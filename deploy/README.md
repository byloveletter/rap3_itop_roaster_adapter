# 라즈베리파이 설치 매뉴얼

로스터 ─ Arduino(SkyCommand) ─ USB ─ **라즈베리파이** ─ 무선랜 ─ PC(Artisan)

이 문서는 빈 SD 카드에서 시작해 라즈베리파이를 로스터 어댑터로 만드는 절차다. 이미 설치된 Pi에 새 버전만 올리려면 [9. 업데이트](#9-업데이트)로 간다.

## 0. 준비물

- Raspberry Pi 3B (다른 모델도 되겠지만 확인한 것은 3B), 전원 어댑터(5V 2.5A 이상)
- microSD 카드 16 GB 이상
- Waveshare 3.5" LCD (A) — 480x320, ILI9486 + XPT2046 감압식 터치
- SkyCommand를 올린 Arduino와 USB 케이블
  - 펌웨어: `SkywalkerRoaster/SkyCommand/SkyCommand.ino`를 Arduino IDE로 그대로 올린다.
  - 로스터 배선: `SkywalkerRoaster/README.md`
- PC: Raspberry Pi Imager, Artisan
- 처음 설치할 때만: HDMI 모니터와 USB 키보드·마우스 (없으면 SSH만으로도 된다)

## 1. SD 카드에 OS 쓰기 (PC)

Raspberry Pi Imager에서:

1. 장치: **Raspberry Pi 3**
2. OS: **Raspberry Pi OS (64-bit)** — 데스크톱이 있는 기본판. Lite는 안 된다(LCD 화면에 데스크톱이 필요하다).
3. 저장소: SD 카드
4. 설정 편집(OS 사용자 지정)에서:
   - 호스트 이름: 예) `raspberrypi`
   - 사용자 이름 `byloveletter`, 비밀번호 설정 — 다른 이름을 써도 되지만 이 문서와 스크립트의 기본값이 `byloveletter`다.
   - 무선랜: SSID와 비밀번호, 국가 **KR**
   - 로캘: 시간대 `Asia/Seoul`, 키보드 `us`
   - 서비스: **SSH 사용**, 비밀번호 인증
5. 쓰기.

검증한 환경은 Debian 13 (trixie) 기반 Raspberry Pi OS, 커널 6.18, labwc(Wayland) 데스크톱이다.

## 2. LCD 끼우고 첫 부팅

1. 전원이 꺼진 상태에서 LCD를 GPIO 헤더의 **1번 핀부터 26번 핀까지** 맞춰 끼운다(보드 모서리 쪽으로 정렬).
2. SD 카드를 넣고 전원을 켠다. 이 단계에서 LCD는 흰 화면이 정상이다(드라이버는 4단계에서 켠다).
3. Pi의 IP 주소를 알아낸다. 다음 중 하나:
   - 공유기 관리 화면의 DHCP 목록
   - HDMI 모니터에서 터미널을 열고 `hostname -I`
   - PC에서 `ping raspberrypi.local`
4. PC에서 접속해 본다: `ssh byloveletter@<Pi IP>`

## 3. 프로그램 받기 (Pi)

SSH(또는 Pi의 터미널)에서:

```bash
git clone https://github.com/byloveletter/rap3_itop_roaster_adapter.git ~/rap3
```

폴더 이름은 반드시 `~/rap3`이다(서비스가 이 경로에서 실행한다). `SkywalkerRoaster/` 서브모듈은 Pi에 필요 없으므로 `--recurse-submodules`는 쓰지 않는다.

인터넷이 안 되면 PC에서 복사한다(저장소 폴더에서): `deploy/push-to-pi.sh byloveletter@<Pi IP>`

## 4. 설치 (Pi)

```bash
cd ~/rap3
deploy/setup.sh               # LCD를 180° 뒤집어 쓸 거면: deploy/setup.sh --rotate 90
sudo reboot
```

`setup.sh`는 sudo 비밀번호를 한 번 묻고 아래 두 스크립트를 차례로 실행한다. 다시 실행해도 안전하다.

**`sudo deploy/install-system.sh`** — 시스템 설정
- 패키지: `python3-pygame python3-serial python3-websockets python3-pytest libts-bin`
- `raspi-config`: SPI 켜기, 부팅 시 데스크톱 자동 로그인, 화면 꺼짐(blanking) 끄기
- 사용자를 `dialout` 그룹에 추가 (Arduino 시리얼 포트 권한)
- `/boot/firmware/config.txt`에 `dtoverlay=piscreen,drm` 추가 (바꾸기 전에 `config.txt.bak-<날짜>`로 백업)
- 터치 보정 도구 설치

**`deploy/install.sh`** — 사용자 설정 (sudo 없이)
- 데스크톱이 뜨면 프로그램이 자동으로 실행되게 한다.
- LCD 터치 매핑과 프로그램 창 전체화면 설정(labwc)
- 바탕화면에 Touch Calibration 아이콘

| 저장소 파일 | Pi에 설치되는 위치 | 스크립트 |
|---|---|---|
| `deploy/roaster-adapter.service` | `~/.config/systemd/user/roaster-adapter.service` | `install.sh` |
| `deploy/roaster-adapter-autostart.desktop` | `~/.config/autostart/roaster-adapter.desktop` | `install.sh` |
| `deploy/labwc-rc.xml` | `~/.config/labwc/rc.xml` (덮어씀) | `install.sh` |
| `deploy/touch-calibrate/touch-calibrate.desktop` | `~/Desktop/touch-calibrate.desktop` | `install.sh` |
| `deploy/touch-calibrate/touch-calibrate` | `/usr/local/sbin/touch-calibrate` | `install-system.sh` |
| `deploy/touch-calibrate/touch-calibrate.service` | `/etc/systemd/system/touch-calibrate.service` | `install-system.sh` |
| (추가되는 줄) `dtoverlay=piscreen,drm` | `/boot/firmware/config.txt` | `install-system.sh` |

## 5. 터치 보정

재부팅하면 LCD에 데스크톱과 로스터 프로그램이 뜬다. 터치는 아직 보정 전이라 위치가 어긋난다.

1. 프로그램 창을 잠시 치우거나(HDMI 모니터의 마우스로) SSH에서 `systemctl --user stop roaster-adapter`
2. LCD 바탕화면의 **Touch Calibration**을 더블클릭한다. 비밀번호 창이 뜨면 sudo 비밀번호를 넣는다.
   - 터치로 아이콘을 누르기 어려우면 SSH에서: `sudo systemctl start touch-calibrate.service`
3. 화면이 꺼졌다가 십자가 5개 차례로 나온다. 십자 한가운데를 펜이나 손톱으로 정확히 누른다.
4. 끝나면 데스크톱이 다시 뜨고 보정이 적용된다. 결과는 `/etc/pointercal`과 `/etc/udev/rules.d/99-ads7846-calibration.rules`에 저장된다.
5. `systemctl --user start roaster-adapter` (또는 재부팅)

## 6. IP 주소 고정

Artisan은 Pi의 IP로 접속하므로 주소가 바뀌지 않게 한다. LCD 온도 아래에 현재 주소(`<IP>:8080`)가 표시된다.

- **권장:** 공유기에서 Pi의 MAC 주소에 IP를 예약(DHCP 고정 할당)한다.
- 공유기를 못 만지면 Pi에서 고정 IP를 설정한다:
  ```bash
  nmcli -t -f NAME,DEVICE con show --active            # 무선랜 연결 이름 확인 (보통 preconfigured)
  sudo nmcli con mod "<연결 이름>" ipv4.method manual \
      ipv4.addresses 172.20.30.181/24 ipv4.gateway <게이트웨이> ipv4.dns <DNS>
  sudo nmcli con up "<연결 이름>"
  ```

## 7. Artisan 설정 (PC)

1. 저장소의 `artisan/skywalker-rpi-websocket.aset`을 PC로 가져온다.
   - Pi 주소가 `172.20.30.181`이 아니면 다시 만든다: `python3 tools/make_artisan_settings.py --host <Pi IP>`
   - 또는 불러온 뒤 Config > Device > WebSocket에서 host를 고친다.
2. Artisan에서 **Help > Load Settings...**로 불러온다.
3. Artisan의 **ON**을 누른다. Pi LCD 상단의 `ART`가 초록색이 되면 연결된 것이다.

## 8. 동작 확인

LCD 상단 표시:
- `ARD` 초록: Arduino 연결됨. 빨강이면 USB 케이블과 `ls /dev/ttyACM* /dev/ttyUSB*`를 확인한다.
- `ART` 초록: Artisan이 온도를 읽어 가는 중. Artisan에서 ON을 눌러야 초록이 된다.
- `ART`가 빨강이면 HEAT/FAN/DRUM/CHARGE/DROP 버튼이 꺼진다(E-STOP, PREHEAT만 동작). Artisan이 10초 동안 온도를 읽어 가지 않으면 로스터를 끈다(워치독).

장비 없이 시험하기 (Pi에서):

```bash
cd ~/rap3
python3 -m pytest -q                 # 테스트
tools/dev-run.sh                     # 가짜 Arduino + LCD 프로그램 (로그 /tmp/ad.log)
python3 tools/fake_artisan.py --interval 1 --script "1:heater 80;3:charge"   # 가짜 Artisan
tools/dev-run.sh stop
systemctl --user start roaster-adapter   # 원래 프로그램 다시 시작
```

## 9. 업데이트

Pi에서:

```bash
cd ~/rap3 && git pull
systemctl --user restart roaster-adapter
```

또는 PC에서 아직 올리지 않은 코드를 복사: `deploy/push-to-pi.sh byloveletter@<Pi IP>` 후 위의 `restart`.

`deploy/` 안의 파일이 바뀌었으면 `deploy/setup.sh`를 다시 실행한다(`labwc-rc.xml`은 덮어쓴다).

## 10. LCD 180° 뒤집기

```bash
cd ~/rap3
sudo deploy/install-system.sh --rotate 90     # 뒤집기
sudo deploy/install-system.sh --rotate 270    # 원래대로
sudo reboot
```

재부팅 후 [5. 터치 보정](#5-터치-보정)을 다시 한다. 화면이 뒤집혀도 터치 센서 좌표는 그대로라서, 보정하기 전까지는 터치가 반대로 잡힌다.

- `rotate` 값은 패널 원래 방향(세로) 기준이다. 270(기본값)과 90이 가로이고, 0과 180은 세로라 프로그램 화면(480x320)이 맞지 않는다.
- 직접 고쳐도 된다: `/boot/firmware/config.txt`의 `dtoverlay=piscreen,drm` 줄을 `dtoverlay=piscreen,drm,rotate=90`으로.
- **아직 실제로 시험하지 않았다.** 재부팅해도 화면이 그대로면 DRM 드라이버가 `rotate`를 받지 않는 것이니 270으로 되돌린다.

## 11. 문제 해결

| 증상 | 확인 |
|---|---|
| LCD가 흰 화면 | `grep piscreen /boot/firmware/config.txt`에 줄이 있는지, 재부팅했는지. LCD가 1–26번 핀에 바르게 끼워졌는지 |
| 부팅 후 화면이 안 나옴 (config.txt 수정 뒤) | SD 카드를 PC에 꽂고 `config.txt`의 `dtoverlay=piscreen...` 줄을 지우거나 `dtoverlay=piscreen,drm`으로 되돌린다. 백업: `config.txt.bak-<날짜>` |
| 터치 위치가 어긋남 / 반대 | 5. 터치 보정 |
| 프로그램이 안 뜸 | `systemctl --user status roaster-adapter`, `journalctl --user -u roaster-adapter -b`. 데스크톱 자동 로그인이 켜져 있는지(`sudo raspi-config` > System > Boot / Auto Login) |
| 프로그램이 HDMI 모니터에 뜸 | `~/.config/labwc/rc.xml`이 `deploy/labwc-rc.xml`과 같은지, 그다음 재부팅 |
| `ARD` 빨강 | USB 케이블, `ls /dev/ttyACM* /dev/ttyUSB*`, `groups`에 `dialout`이 있는지(추가 직후라면 재부팅) |
| `ART` 빨강 | Artisan에서 ON을 눌렀는지, Artisan의 WebSocket host/port가 LCD에 보이는 주소와 같은지, PC와 Pi가 같은 네트워크인지 |
| LCD가 몇 분 뒤 꺼짐 | `sudo raspi-config nonint do_blanking 1` 후 재부팅 |
