
[app]
title = HATIM 5G
package.name = hatim5g
package.domain = com.hatim

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,txt,json

version = 0.1.0

requirements = python3,kivy==2.3.0,requests

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/assets/icon.png

android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.archs = arm64-v8a

p4a.bootstrap = sdl2
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1
