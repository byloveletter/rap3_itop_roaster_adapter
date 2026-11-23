# 라즈베리파이 설치

대상: Raspberry Pi 3B, Raspberry Pi OS(Debian 13 trixie, 데스크톱), 사용자 `byloveletter`, Waveshare 3.5" LCD.

## 1. 파일 복사

라즈베리파이의 `~/rap3/` 아래에 저장소의 다음 폴더를 복사한다. `ref/`, `artisan/`, `SkywalkerRoaster/`는 PC용이라 필요 없다.

```
~/rap3/roaster_adapter/   프로그램
~/rap3/deploy/            설치 파일
~/rap3/tools/             시뮬레이터, 개발용 스크립트
~/rap3/tests/             테스트
```

PC에서 (저장소 폴더):

```bash
rsync -a --delete --exclude __pycache__ --exclude .pytest_cache \
  roaster_adapter tools tests deploy byloveletter@<Pi IP>:rap3/
```

또는 Pi에서 `git clone` 한 뒤 `~/rap3`로 이름을 바꿔도 된다.

## 2. 처음 설치

Pi에서:

```bash
cd ~/rap3
sudo deploy/install-system.sh            # 패키지, LCD 설정, 터치 보정 도구
deploy/install.sh                        # 자동 실행, labwc 설정, 바탕화면 아이콘 (sudo 없이)
sudo reboot
```

재부팅 후 바탕화면의 **Touch Calibration**을 더블클릭해서 터치를 보정한다(비밀번호 창이 뜨면 sudo 비밀번호). 화면이 꺼졌다가 십자 5개가 차례로 나오면 정확히 누른다.

| 저장소 파일 | Pi에 설치되는 위치 | 설치 스크립트 |
|---|---|---|
| `deploy/roaster-adapter.service` | `~/.config/systemd/user/roaster-adapter.service` | `install.sh` |
| `deploy/roaster-adapter-autostart.desktop` | `~/.config/autostart/roaster-adapter.desktop` | `install.sh` |
| `deploy/labwc-rc.xml` | `~/.config/labwc/rc.xml` (덮어씀) | `install.sh` |
| `deploy/touch-calibrate/touch-calibrate.desktop` | `~/Desktop/touch-calibrate.desktop` | `install.sh` |
| `deploy/touch-calibrate/touch-calibrate` | `/usr/local/sbin/touch-calibrate` | `install-system.sh` |
| `deploy/touch-calibrate/touch-calibrate.service` | `/etc/systemd/system/touch-calibrate.service` | `install-system.sh` |
| (생성) `dtoverlay=piscreen,drm` 줄 | `/boot/firmware/config.txt` | `install-system.sh` |

터치 보정 결과는 `/etc/pointercal`과 `/etc/udev/rules.d/99-ads7846-calibration.rules`에 저장된다.

## 3. 업데이트 (프로그램만 바뀐 경우)

1번처럼 복사한 뒤 Pi에서:

```bash
systemctl --user restart roaster-adapter
journalctl --user -u roaster-adapter -f       # 로그, Ctrl+C로 종료
```

`deploy/` 안의 파일이 바뀌었으면 `deploy/install.sh`를 다시 실행한다.

## 4. LCD 180° 뒤집기

```bash
cd ~/rap3
sudo deploy/install-system.sh --rotate 90     # 뒤집기
sudo deploy/install-system.sh --rotate 270    # 원래대로
sudo reboot
```

재부팅 후 **Touch Calibration**을 다시 한다. 화면이 뒤집혀도 터치 센서 좌표는 그대로라서, 보정하기 전까지는 터치가 반대로 잡힌다. 아이콘을 누르기 어려우면 SSH에서 `sudo systemctl start touch-calibrate.service`.

- `rotate` 값은 패널 원래 방향(세로) 기준이다. 270(기본값)과 90이 가로이고, 0과 180은 세로라 프로그램 화면(480x320)이 맞지 않는다.
- 스크립트는 `config.txt`를 바꾸기 전에 `config.txt.bak-<날짜>`로 백업한다.
- 직접 고쳐도 된다: `/boot/firmware/config.txt`의 `dtoverlay=piscreen,drm` 줄을 `dtoverlay=piscreen,drm,rotate=90`으로.
- 아직 실제로 시험하지 않았다. 재부팅해도 화면이 그대로면 DRM 드라이버가 `rotate`를 받지 않는 것이니 270으로 되돌린다. 화면이 안 나오면 SD 카드를 PC에 꽂고 `config.txt`의 그 줄을 `dtoverlay=piscreen,drm`으로 되돌린다.

## 5. 확인

- LCD에 로스터 화면이 전체화면으로 뜨고, 온도 아래에 `<IP>:8080`이 보인다. 이 주소를 Artisan의 Config > Device > WebSocket host/port에 넣는다(`artisan/skywalker-rpi-websocket.aset`을 불러오면 172.20.30.181:8080).
- 상단 `ARD`: Arduino 연결, `ART`: Artisan이 온도를 읽어 가는 중(Artisan에서 ON을 눌러야 초록).
- `ART`가 빨간색이면 HEAT/FAN/DRUM/CHARGE/DROP 버튼은 꺼져 있다(E-STOP, PREHEAT만 동작).
- 시뮬레이터로 시험: `tools/dev-run.sh` (끝낼 때 `tools/dev-run.sh stop`, 그다음 `systemctl --user start roaster-adapter`).
