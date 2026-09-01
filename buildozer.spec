[app]

title = 三面向股票分析器

package.name = stockthreefactor

package.domain = org.example

source.dir = .

source.include_exts = py,txt

version = 1.0.0

requirements = python3,kivy==2.3.0,requests,cython==0.29.33

orientation = portrait

fullscreen = 0

android.api = 35

android.minapi = 23

android.archs = arm64-v8a, armeabi-v7a

android.permissions = INTERNET

android.accept_sdk_license = True

android.ndk = 25b

[buildozer]

log_level = 2

warn_on_root = 1
