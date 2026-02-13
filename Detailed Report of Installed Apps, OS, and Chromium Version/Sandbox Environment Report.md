# Sandbox Environment Report

This report details the specifications and installed software within the sandbox environment as of February 12, 2026.

## 1. Operating System and System Information

```
OS Information:
PRETTY_NAME="Ubuntu 22.04.5 LTS"
Kernel: 6.1.102 #1 SMP PREEMPT_DYNAMIC Tue Sep 3 09:03:50 UTC 2024 x86_64
Architecture: x86_64
CPU: Intel(R) Xeon(R) Processor @ 2.50GHz (6 cores)
Memory: 3.8Gi Total
Disk: 42G Total, 32G Available
Uptime: 1 day, 14 hours
```

## 2. Installed Packages and Applications

### 2.1 APT Packages

Below is a partial list of APT packages installed in the environment. A complete list is available in the attached `apt_packages.txt` file.

```
adduser 3.118ubuntu5
adwaita-icon-theme 41.0-1ubuntu1
apt 2.4.14
apt-transport-https 2.4.14
base-files 12ubuntu4.7
base-passwd 3.5.52build1
bash 5.1-6ubuntu1.1
bc 1.07.1-3build1
bsdutils 1:2.37.2-4ubuntu3.4
ca-certificates 20240203~22.04.1
ca-certificates-java 20190909ubuntu1.2
chromium-browser 1:128.0.6613.137-0ubuntu0.22.04.1sav0
chromium-codecs-ffmpeg-extra 1:128.0.6613.137-0ubuntu0.22.04.1sav0
chrony 4.2-2ubuntu2
code-server 4.104.3
coreutils 8.32-4.1ubuntu1.2
cpp 4:11.2.0-1ubuntu1
cpp-11 11.4.0-1ubuntu1~22.04.2
curl 7.81.0-1ubuntu1.21
dash 0.5.11+git20210903+057cd650a4ed-3build1
dbus 1.12.20-2ubuntu4.1
dbus-x11 1.12.20-2ubuntu4.1
dconf-gsettings-backend 0.40.0-3ubuntu0.1
dconf-service 0.40.0-3ubuntu0.1
debconf 1.5.79ubuntu1
debianutils 5.5-1ubuntu2
default-jre 2:1.11-72build2
default-jre-headless 2:1.11-72build2
diffutils 1:3.8-0ubuntu2
dirmngr 2.2.27-3ubuntu2.4
dpkg 1.21.1ubuntu2.6
e2fsprogs 1.46.5-2ubuntu1.2
ffmpeg 7:4.4.2-0ubuntu0.22.04.1
file 1:5.41-3ubuntu0.1
findutils 4.8.0-1ubuntu3
fontconfig 2.13.1-4.2ubuntu5
fontconfig-config 2.13.1-4.2ubuntu5
fonts-droid-fallback 1:6.0.1r16-1.1build1
fonts-hosny-amiri 0.113-1
fonts-ipafont-gothic 00303-21ubuntu1
fonts-liberation 1:1.07.4-11
fonts-lohit-deva 2.95.4-4
fonts-lohit-gujr 2.92.4-4
fonts-lohit-taml 2.91.3-2
fonts-noto 20201225-1build1
fonts-noto-cjk 1:20220127+repack1-1
fonts-noto-cjk-extra 1:20220127+repack1-1
fonts-noto-color-emoji 2.047-0ubuntu0.22.04.1
fonts-noto-core 20201225-1build1
fonts-noto-extra 20201225-1build1
fonts-opensymbol 2:102.12+LibO7.3.7-0ubuntu0.22.04.10
fonts-sil-abyssinica 2.100-3
fonts-sil-padauk 5.000-3
fonts-sil-scheherazade 2.100-3
fonts-thai-tlwg 1:0.7.3-1
fonts-tlwg-garuda 1:0.7.3-1
fonts-tlwg-garuda-ttf 1:0.7.3-1
fonts-tlwg-kinnari 1:0.7.3-1
fonts-tlwg-kinnari-ttf 1:0.7.3-1
fonts-tlwg-laksaman 1:0.7.3-1
fonts-tlwg-laksaman-ttf 1:0.7.3-1
fonts-tlwg-loma 1:0.7.3-1
fonts-tlwg-loma-ttf 1:0.7.3-1
fonts-tlwg-mono 1:0.7.3-1
fonts-tlwg-mono-ttf 1:0.7.3-1
fonts-tlwg-norasi 1:0.7.3-1
fonts-tlwg-norasi-ttf 1:0.7.3-1
fonts-tlwg-purisa 1:0.7.3-1
fonts-tlwg-purisa-ttf 1:0.7.3-1
fonts-tlwg-sawasdee 1:0.7.3-1
fonts-tlwg-sawasdee-ttf 1:0.7.3-1
fonts-tlwg-typewriter 1:0.7.3-1
fonts-tlwg-typewriter-ttf 1:0.7.3-1
fonts-tlwg-typist 1:0.7.3-1
fonts-tlwg-typist-ttf 1:0.7.3-1
fonts-tlwg-typo 1:0.7.3-1
fonts-tlwg-typo-ttf 1:0.7.3-1
fonts-tlwg-umpush 1:0.7.3-1
fonts-tlwg-umpush-ttf 1:0.7.3-1
fonts-tlwg-waree 1:0.7.3-1
fonts-tlwg-waree-ttf 1:0.7.3-1
fonts-wqy-microhei 0.2.0-beta-3.1
fonts-wqy-zenhei 0.9.45-8
gcc-11-base 11.4.0-1ubuntu1~22.04.2
gcc-12-base 12.3.0-1ubuntu1~22.04.2
gh 2.81.0
gir1.2-gdkpixbuf-2.0 2.42.8+dfsg-1ubuntu0.4
gir1.2-glib-2.0 1.72.0-1
gir1.2-notify-0.7 0.7.9-3ubuntu5.22.04.1
git 1:2.34.1-1ubuntu1.15
git-man 1:2.34.1-1ubuntu1.15
glib-networking 2.72.0-1
glib-networking-common 2.72.0-1
glib-networking-services 2.72.0-1
gnupg 2.2.27-3ubuntu2.4
gnupg-l10n 2.2.27-3ubuntu2.4
gnupg-utils 2.2.27-3ubuntu2.4
gnupg2 2.2.27-3ubuntu2.4
gpg 2.2.27-3ubuntu2.4
gpg-agent 2.2.27-3ubuntu2.4
gpg-wks-client 2.2.27-3ubuntu2.4
gpg-wks-server 2.2.27-3ubuntu2.4
gpgconf 2.2.27-3ubuntu2.4
gpgsm 2.2.27-3ubuntu2.4
gpgv 2.2.27-3ubuntu2.4
graphviz 2.42.2-6ubuntu0.1
grep 3.7-1build1
gsettings-desktop-schemas 42.0-1ubuntu1
gstreamer1.0-libav 1.20.3-0ubuntu1
gstreamer1.0-plugins-bad 1.20.3-0ubuntu1.1
gstreamer1.0-plugins-base 1.20.1-1ubuntu0.5
gstreamer1.0-plugins-good 1.20.3-0ubuntu1.4
gstreamer1.0-plugins-ugly 1.20.1-1
gstreamer1.0-tools 1.20.3-0ubuntu1.1
gtk-update-icon-cache 3.24.33-1ubuntu2.2
gzip 1.10-4ubuntu4.1
hicolor-icon-theme 0.17-2
hostname 3.23ubuntu2
humanity-icon-theme 0.6.16
init-system-helpers 1.62
iproute2 5.15.0-1ubuntu2
iptables 1.8.7-1ubuntu5.2
iso-codes 4.9.0-1
java-common 0.72build2
jq 1.6-2.1ubuntu3.1
keyboard-configuration 1.205ubuntu3
less 590-1ubuntu0.22.04.3
liba52-0.7.4 0.7.4-20
libaa1 1.4p5-50build1
libabsl20210324 0~20210324.2-2ubuntu0.2
libabw-0.1-1 0.1.3-1build3
libacl1 2.3.1-1
libann0 1.1.2+doc-7build1
libaom3 3.3.0-1ubuntu0.1
libapparmor1 3.0.4-2ubuntu2.4
libapt-pkg6.0 2.4.14
libargon2-1 0~20171227-0.3
libasound2 1.2.6.1-1ubuntu1
libasound2-data 1.2.6.1-1ubuntu1
libasound2-plugins 1.2.6-1
libass9 1:0.15.2-1
libassuan0 2.5.5-1build1
libasyncns0 0.8-6build2
libatk-bridge2.0-0 2.38.0-3
libatk1.0-0 2.36.0-3build1
libatk1.0-data 2.36.0-3build1
libatspi2.0-0 2.44.0-3
libattr1 1:2.5.1-1build1
libaudit-common 1:3.0.7-1build1
libaudit1 1:3.0.7-1build1
libavahi-client3 0.8-5ubuntu5.2
libavahi-common-data 0.8-5ubuntu5.2
libavahi-common3 0.8-5ubuntu5.2
libavc1394-0 0.5.4-5build2
libavcodec58 7:4.4.2-0ubuntu0.22.04.1
libavdevice58 7:4.4.2-0ubuntu0.22.04.1
libavfilter7 7:4.4.2-0ubuntu0.22.04.1
libavformat58 7:4.4.2-0ubuntu0.22.04.1
libavutil56 7:4.4.2-0ubuntu0.22.04.1
libblas3 3.10.0-2ubuntu1
libblkid-dev 2.37.2-4ubuntu3.4
libblkid1 2.37.2-4ubuntu3.4
libbluray2 1:1.3.1-1
libboost-filesystem1.74.0 1.74.0-14ubuntu3
libboost-iostreams1.74.0 1.74.0-14ubuntu3
libboost-locale1.74.0 1.74.0-14ubuntu3
libboost-thread1.74.0 1.74.0-14ubuntu3
libbpf0 1:0.5.0-1ubuntu22.04.1
libbrotli-dev 1.10-2build6
libbrotli1 1.10-2build6
libbs2b0 3.1.0+dfsg-2.2build1
libbsd0 0.11.5-1
libbz2-1.0 1.0.8-5build1
libc-bin 2.35-0ubuntu3.11
libc-dev-bin 2.35-0ubuntu3.11
libc6 2.35-0ubuntu3.11
libc6-dev 2.35-0ubuntu3.11
libcaca0 0.99.beta19-2.2ubuntu4
libcairo-gobject2 1.16.0-5ubuntu2
libcairo2 1.16.0-5ubuntu2
libcap-ng0 0.7.9-2.2build3
libcap2 1:2.44-1ubuntu0.22.04.2
libcap2-bin 1:2.44-1ubuntu0.22.04.2
libcbor0.8 0.8.0-2ubuntu1
libcdio-cdda2 10.2+2.0.0-1build3
libcdio-paranoia2 10.2+2.0.0-1build3
libcdio19 2.1.0-3ubuntu0.2
libcdparanoia0 3.10.2+debian-14build2
libcdr-0.1-1 0.1.6-2build2
libcdt5 2.42.2-6ubuntu0.1
libcgraph6 2.42.2-6ubuntu0.1
libchromaprint1 1.5.1-2
libclucene-contribs1v5 2.3.3.4+dfsg-1ubuntu5
libclucene-core1v5 2.3.3.4+dfsg-1ubuntu5
libcodec2-1.0 1.0.1-3
libcolamd2 1:5.10.1+dfsg-4build1
libcolord2 1.4.6-1
libcom-err2 1.46.5-2ubuntu1.2
libcrypt-dev 1:4.4.27-1
libcrypt1 1:4.4.27-1
libcryptsetup12 2:2.4.3-1ubuntu1.3
libcups2 2.4.1op1-1ubuntu4.12
libcurl3-gnutls 7.81.0-1ubuntu1.21
libcurl4 7.81.0-1ubuntu1.21
libdatrie1 0.2.13-2
libdav1d5 0.9.2-1
libdb5.3 5.3.28+dfsg1-0.8ubuntu3
libdbus-1-3 1.12.20-2ubuntu4.1
libdc1394-25 2.2.6-4
libdca0 0.0.7-2
libdconf1 0.40.0-3ubuntu0.1
libde265-0 1.0.8-1ubuntu0.3
libdebconfclient0 0.261ubuntu1
libdecor-0-0 0.1.0-3build1
libdeflate-dev 1.10-2
libdeflate0 1.10-2
libdevmapper1.02.1 2:1.02.175-2.1ubuntu5
libdmx-dev 1:1.1.4-2build2
libdmx1 1:1.1.4-2build2
libdpkg-perl 1.21.1ubuntu2.6
libdrm-amdgpu1 2.4.113-2~ubuntu0.22.04.1
libdrm-common 2.4.113-2~ubuntu0.22.04.1
libdrm-dev 2.4.113-2~ubuntu0.22.04.1
libdrm-intel1 2.4.113-2~ubuntu0.22.04.1
libdrm-nouveau2 2.4.113-2~ubuntu0.22.04.1
libdrm-radeon1 2.4.113-2~ubuntu0.22.04.1
libdrm2 2.4.113-2~ubuntu0.22.04.1
libdv4 1.0.0-14build1
libdvdnav4 6.1.1-1
libdvdread8 6.1.2-1
libdw1 0.186-1ubuntu0.1
libe-book-0.1-1 0.1.3-2build2
libedit2 3.1-20210910-1build1
libegl-mesa0 23.2.1-1ubuntu3.1~22.04.3
libegl1 1.4.0-1
libelf1 0.186-1ubuntu0.1
libeot0 0.01-5build2
libepoxy0 1.5.10-1
libepubgen-0.1-1 0.1.1-1ubuntu5
liberror-perl 0.17029-1
libetonyek-0.1-1 0.1.10-3build1
libevdev2 1.12.1+dfsg-1
libexpat1 2.4.7-1ubuntu0.6
libexpat1-dev 2.4.7-1ubuntu0.6
libext2fs2 1.46.5-2ubuntu1.2
libexttextcat-2.0-0 3.4.5-1build2
libexttextcat-data 3.4.5-1build2
libfaad2 2.10.0-2
libffi-dev 3.4.2-4
libffi8 3.4.2-4
libfftw3-single3 3.3.8-2ubuntu8
libfido2-1 1.10.0-1
libflac8 1.3.3-2ubuntu0.2
libflite1 2.2-3
libfluidsynth3 2.2.5-1
libfontconfig-dev 2.13.1-4.2ubuntu5
libfontconfig1 2.13.1-4.2ubuntu5
libfontconfig1-dev 2.13.1-4.2ubuntu5
libfontenc-dev 1:1.1.4-1build3
libfontenc1 1:1.1.4-1build3
libfreeaptx0 0.1.1-1
libfreehand-0.1-1 0.1.2-3build2
libfreetype-dev 2.11.1+dfsg-1ubuntu0.3
libfreetype6 2.11.1+dfsg-1ubuntu0.3
libfreetype6-dev 2.11.1+dfsg-1ubuntu0.3
libfribidi0 1.0.8-2ubuntu3.1
libfs-dev 2:1.0.8-1build2
libfs6 2:1.0.8-1build2
libgbm-dev 23.2.1-1ubuntu3.1~22.04.3
libgbm1 23.2.1-1ubuntu3.1~22.04.3
libgcc-s1 12.3.0-1ubuntu1~22.04.2
libgcrypt20 1.9.4-3ubuntu3
libgd3 2.3.0-2ubuntu2.3
libgdbm-compat4 1.23-1
libgdbm6 1.23-1
libgdk-pixbuf-2.0-0 2.42.8+dfsg-1ubuntu0.4
libgdk-pixbuf-2.0-dev 2.42.8+dfsg-1ubuntu0.4
libgdk-pixbuf-xlib-2.0-0 2.40.2-2build4
libgdk-pixbuf2.0-0 2.40.2-2build4
libgdk-pixbuf2.0-bin 2.42.8+dfsg-1ubuntu0.4
libgdk-pixbuf2.0-common 2.42.8+dfsg-1ubuntu0.4
libgfortran5 12.3.0-1ubuntu1~22.04.2
libgif7 5.1.9-2ubuntu0.1
libgirepository-1.0-1 1.72.0-1
libgl-dev 1.4.0-1
libgl1 1.4.0-1
libgl1-mesa-dri 23.2.1-1ubuntu3.1~22.04.3
libglapi-mesa 23.2.1-1ubuntu3.1~22.04.3
libgles2 1.4.0-1
libglib2.0-0 2.72.4-0ubuntu2.6
libglib2.0-bin 2.72.4-0ubuntu2.6
libglib2.0-data 2.72.4-0ubuntu2.6
libglib2.0-dev 2.72.4-0ubuntu2.6
libglib2.0-dev-bin 2.72.4-0ubuntu2.6
libglvnd0 1.4.0-1
libglx-dev 1.4.0-1
libglx-mesa0 23.2.1-1ubuntu3.1~22.04.3
libglx0 1.4.0-1
libgme0 0.6.3-2
libgmp10 2:6.2.1+dfsg-3ubuntu1
libgnutls30 3.7.3-4ubuntu1.7
libgomp1 12.3.0-1ubuntu1~22.04.2
libgpg-error0 1.43-3
libgpgme11 1.16.0-1.2ubuntu4.2
libgpgmepp6 1.16.0-1.2ubuntu4.2
libgpm2 1.20.7-10build1
libgraphite2-3 1.3.14-1build2
libgsm1 1.0.19-1
libgssapi-krb5-2 1.19.2-2ubuntu0.7
libgssdp-1.2-0 1.4.0.1-2build1
libgstreamer-gl1.0-0 1.20.1-1ubuntu0.5
libgstreamer-plugins-bad1.0-0 1.20.3-0ubuntu1.1
libgstreamer-plugins-base1.0-0 1.20.1-1ubuntu0.5
libgstreamer-plugins-good1.0-0 1.20.3-0ubuntu1.4
libgstreamer1.0-0 1.20.3-0ubuntu1.1
libgtk-3-0 3.24.33-1ubuntu2.2
libgtk-3-common 3.24.33-1ubuntu2.2
libgtk2.0-0 2.24.33-2ubuntu2.1
libgtk2.0-common 2.24.33-2ubuntu2.1
libgts-0.7-5 0.7.6+darcs121130-5
libgudev-1.0-0 1:237-2build1
libgupnp-1.2-1 1.4.3-1
libgupnp-igd-1.0-4 1.2.0-1build1
libgvc6 2.42.2-6ubuntu0.1
libgvpr2 2.42.2-6ubuntu0.1
libharfbuzz-icu0 2.7.4-1ubuntu3.2
libharfbuzz0b 2.7.4-1ubuntu3.2
libhogweed6 3.7.3-1build2
libhunspell-1.7-0 1.7.0-4build1
libhyphen0 2.8.8-7build2
libice-dev 2:1.0.10-1build2
libice6 2:1.0.10-1build2
libicu70 70.1-2
libid3tag0 0.15.1b-14
```

### 2.2 Python Packages (pip)

Below is a list of Python packages installed via pip. A complete list is available in the attached `pip_packages.txt` file.

```
Package               Version
--------------------- -----------
annotated-types       0.7.0
anyio                 4.11.0
arabic-reshaper       3.0.0
asn1crypto            1.5.1
beautifulsoup4        4.14.2
blinker               1.9.0
boto3                 1.40.51
botocore              1.40.51
brotli                1.1.0
certifi               2025.10.5
cffi                  2.0.0
charset-normalizer    3.4.4
click                 8.3.0
contourpy             1.3.3
cryptography          46.0.2
cssselect2            0.8.0
cycler                0.12.1
defusedxml            0.7.1
distro                1.9.0
et-xmlfile            2.0.0
fastapi               0.119.0
flask                 3.1.2
fonttools             4.60.1
fpdf                  1.7.2
fpdf2                 2.8.4
git-remote-s3         0.2.5
greenlet              3.2.4
h11                   0.16.0
html5lib              1.1
httpcore              1.0.9
httpx                 0.28.1
idna                  3.11
itsdangerous          2.2.0
jinja2                3.1.6
jiter                 0.11.0
jmespath              1.0.1
kiwisolver            1.4.9
lxml                  6.0.2
markdown              3.9
markupsafe            3.0.3
matplotlib            3.10.7
narwhals              2.8.0
numpy                 2.3.3
openai                2.3.0
openpyxl              3.1.5
oscrypto              1.3.0
packaging             25.0
pandas                2.3.3
pdf2image             1.17.0
pillow                11.3.0
playwright            1.55.0
plotly                6.3.1
pycparser             2.23
pydantic              2.12.1
pydantic-core         2.41.3
pydyf                 0.11.0
pyee                  13.0.0
pyhanko               0.31.0
pyhanko-certvalidator 0.29.0
pyparsing             3.2.5
pypdf                 6.1.1
pyphen                0.17.2
python-bidi           0.6.6
python-dateutil       2.9.0.post0
pytz                  2025.2
pyyaml                6.0.3
reportlab             4.4.4
requests              2.32.5
s3transfer            0.14.0
seaborn               0.13.2
six                   1.17.0
sniffio               1.3.1
soupsieve             2.8
starlette             0.48.0
svglib                1.5.1
tabulate              0.9.0
tinycss2              1.4.0
tinyhtml5             2.0.0
tqdm                  4.67.1
typing-extensions     4.15.0
typing-inspection     0.4.2
tzdata                2025.2
tzlocal               5.3.1
uritools              5.0.0
urllib3               2.5.0
uvicorn               0.37.0
weasyprint            66.0
webencodings          0.5.1
werkzeug              3.1.3
xhtml2pdf             0.2.17
zopfli                0.2.3.post1
```

### 2.3 Node.js Packages (npm)

Below is a list of globally installed Node.js packages. A complete list is available in the attached `npm_packages.txt` file.

```
/home/ubuntu/.nvm/versions/node/v22.13.0/lib
├── corepack@0.30.0
├── npm@10.9.2
└── pnpm@10.29.2
```

## 3. Development Environment Details

| Tool          | Version         |
|---------------|-----------------|
| Chromium      | 128.0.6613.137  |
| Python        | 3.11.0rc1       |
| Node.js       | v22.13.0        |
| NPM           | 10.9.2          |
| PNPM          | 10.29.2         |
| Git           | 2.34.1          |
| Curl          | 7.81.0          |
| Wget          | 1.21.2          |
