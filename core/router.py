from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import requests

from core.parsers import SignalParseError, parse_cell_info, parse_signal_response

DEFAULT_ROUTER_URL = "http://192.168.9.1"


class RouterError(Exception):
    """A user-displayable router communication error."""


class RouterUnreachableError(RouterError):
    pass


class RouterLoginError(RouterError):
    pass


class RouterSignalError(RouterError):
    pass


@dataclass(frozen=True)
class RouterReading:
    signal: dict[str, dict[str, str]]
    cell_info: dict[str, str]
    login_verified: bool


class HuaweiRouter:
    """Huawei HiLink web API client with a cookie-preserving HTTP session."""

    def __init__(self, address: str, password: str = "", timeout: float = 8) -> None:
        address = address.strip() or DEFAULT_ROUTER_URL
        if "://" not in address:
            address = "http://" + address
        parsed = urlparse(address)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RouterUnreachableError("أدخل عنوان راوتر صحيحًا مثل http://192.168.9.1")
        self.base_url = urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "HATIM5G/1.0",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/xml, text/xml, */*",
        })
        self.tokens: list[str] = []

    def close(self) -> None:
        self.session.close()

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        headers = dict(kwargs.pop("headers", {}))
        if self.tokens:
            headers["__RequestVerificationToken"] = self.tokens.pop(0) if len(self.tokens) > 1 else self.tokens[0]
        try:
            response = self.session.request(
                method,
                f"{self.base_url}/{path.lstrip('/')}",
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            if status in {401, 403}:
                raise RouterLoginError("رفض الراوتر الطلب؛ تحقق من كلمة المرور وصلاحية الحساب.") from exc
            raise RouterError(f"رفض الراوتر الطلب (HTTP {status}).") from exc
        except requests.exceptions.RequestException as exc:
            raise RouterUnreachableError(
                "تعذر الوصول إلى الراوتر. تحقق من اتصال الهاتف بشبكته وعنوانه."
            ) from exc

        error_code = re.search(r"<(?:\w+:)?code>\s*(\d+)\s*</(?:\w+:)?code>", response.text, re.IGNORECASE)
        if error_code and error_code.group(1) == "100003":
            raise RouterLoginError("يتطلب الراوتر تسجيل الدخول قبل السماح بهذا الطلب.")
        self._update_tokens(response)
        return response

    def _update_tokens(self, response: requests.Response) -> None:
        one = response.headers.get("__RequestVerificationTokenone")
        two = response.headers.get("__RequestVerificationTokentwo")
        single = response.headers.get("__RequestVerificationToken")
        if one:
            self.tokens = [one] + ([two] if two else [])
        elif single:
            self.tokens = [single]

    @staticmethod
    def _xml_fields(body: str) -> dict[str, str]:
        from core.parsers import flatten_response

        return flatten_response(body)

    def _prime_session(self) -> None:
        try:
            homepage = self.session.get(self.base_url + "/", timeout=self.timeout)
            homepage.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise RouterUnreachableError(
                "تعذر الوصول إلى الراوتر. اتصل بشبكته وتحقق من العنوان."
            ) from exc

        self._update_tokens(homepage)
        match = re.search(
            r'<meta\s+name=["\']csrf_token["\']\s+content=["\']([^"\']+)',
            homepage.text,
            flags=re.IGNORECASE,
        )
        if match:
            self.tokens = [match.group(1)]
        else:
            try:
                token_response = self._request("GET", "/api/webserver/token")
            except RouterUnreachableError:
                raise
            except RouterError:
                try:
                    token_response = self._request("GET", "/api/webserver/SesTokInfo")
                except RouterUnreachableError:
                    raise
                except RouterError:
                    return
            fields = self._xml_fields(token_response.text)
            session_info = fields.get("sesinfo")
            if session_info:
                host = urlparse(self.base_url).hostname
                self.session.cookies.set("SessionID", session_info, domain=host, path="/")
            token = fields.get("token") or fields.get("tokinfo")
            if token:
                self.tokens = [token]

    def _login_if_needed(self) -> bool:
        if not self.password:
            return False
        try:
            state_response = self._request("GET", "/api/user/state-login")
            fields = self._xml_fields(state_response.text)
            state = fields.get("state")
            password_type = int(fields.get("passwordtype", "0"))
        except RouterError as exc:
            raise RouterLoginError(f"تعذر التحقق من جلسة تسجيل الدخول: {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise RouterLoginError("رد حالة تسجيل الدخول غير مفهوم.") from exc

        if state == "1":
            return True
        if not self.tokens:
            raise RouterLoginError("لم يُرجع الراوتر رمز حماية صالحًا لتسجيل الدخول.")

        if password_type == 4:
            csrf = self.tokens[0]
            password_hash = base64.b64encode(hashlib.sha256(self.password.encode("utf-8")).hexdigest().encode("ascii"))
            credentials = b"admin" + password_hash + csrf.encode("utf-8")
            encoded_password = base64.b64encode(hashlib.sha256(credentials).hexdigest().encode("ascii")).decode("ascii")
        else:
            encoded_password = base64.b64encode(self.password.encode("utf-8")).decode("ascii")

        body = (
            "<request><Username>admin</Username>"
            f"<Password>{encoded_password}</Password>"
            f"<password_type>{password_type}</password_type></request>"
        )
        try:
            login_response = self._request(
                "POST",
                "/api/user/login",
                data=body.encode("utf-8"),
                headers={"Content-Type": "application/xml"},
            )
        except RouterError as exc:
            raise RouterLoginError(f"فشل تسجيل الدخول إلى الراوتر: {exc}") from exc

        fields = self._xml_fields(login_response.text)
        error_code = fields.get("code", "")
        if error_code in {"108001", "108002", "108006", "100003"}:
            raise RouterLoginError("فشلت كلمة المرور أو لا يملك الحساب صلاحية الدخول.")
        if fields.get("response", "").upper() != "OK":
            raise RouterLoginError("لم يؤكد الراوتر نجاح تسجيل الدخول.")
        return True

    def read_signal(self) -> RouterReading:
        self._prime_session()
        login_verified = self._login_if_needed()
        try:
            signal_response = self._request("GET", "/api/device/signal")
            signal = parse_signal_response(signal_response.text)
        except SignalParseError as exc:
            raise RouterSignalError(str(exc)) from exc
        except RouterError as exc:
            if isinstance(exc, RouterUnreachableError):
                raise
            if isinstance(exc, RouterLoginError):
                raise
            raise RouterSignalError(f"تعذر طلب بيانات الإشارة: {exc}") from exc

        try:
            cell_response = self._request("GET", "/api/net/cell-info")
            cell_info = parse_cell_info(cell_response.text)
        except RouterError:
            cell_info = {}
        return RouterReading(signal, cell_info, login_verified)

    @classmethod
    def test_connection(
        cls, address: str, password: str = "", timeout: float = 8
    ) -> RouterReading:
        client = cls(address, password, timeout)
        try:
            return client.read_signal()
        finally:
            client.close()
