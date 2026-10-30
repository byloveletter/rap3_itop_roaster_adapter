# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 목표

요구사항 원문은 `project.md`에 있다. Skywalker(ITOP MTCR) 커피 로스터와 PC의 Artisan 사이에 라즈베리파이를 넣어 무선으로 연결한다.

```
로스터 ─(유선)─ Arduino (SkyCommand) ─(USB 시리얼)─ 라즈베리파이 ─(무선랜, WebSocket)─ PC (Artisan)
```

개발 대상은 두 가지다.
1. **라즈베리파이 프로그램**
   - Arduino와 Artisan 사이에서 명령과 데이터를 중계한다.
   - Waveshare 3.5인치 LCD(320x480, XPT2046 터치)에 Artisan과 같은 온도를 표시한다(아래 "표시 온도" 참고).
   - 터치로 히터·팬 조정, ESTOP, 투입(CHARGE), 배출(DROP)을 제어한다.
2. **Artisan 기본 설정** (`.aset`): `SkywalkerRoaster/ArtisanConfigs/`를 참고해서 만든다.

## 코드 구조와 명령

라즈베리파이 프로그램은 `roaster_adapter/` 패키지다(Python 3, pygame, websockets, pyserial). 이 PC에는 venv가 없어서 실행과 테스트는 라즈베리파이(Raspberry Pi 3B, Debian 13, Python 3.13)에서 한다. 코드는 rsync로 `~/rap3/`에 올린다.

```
# 동기화 (이 PC에서)
sshpass -p <pw> rsync -a --delete --exclude __pycache__ --exclude .pytest_cache roaster_adapter tools tests deploy byloveletter@172.20.30.181:rap3/
# 테스트 (Pi의 ~/rap3에서)
python3 -m pytest -q
python3 -m pytest -q tests/test_preheat.py::test_full_sequence
# 시뮬레이터 + LCD UI 실행 / 중지 (Pi)
tools/dev-run.sh [--preheat-hold 20]     # 로그: /tmp/ad.log(프로그램), /tmp/fa.log(시뮬레이터)
tools/dev-run.sh stop
# Artisan 대신 테스트 클라이언트 (Pi)
python3 tools/fake_artisan.py --interval 1 --script "1:heater 80;3:charge"
# 실제 장비 (--serial 기본값 auto: /dev/ttyACM* 다음 /dev/ttyUSB*)
python3 -m roaster_adapter [--serial /dev/ttyACM0] [--windowed] [--no-ui] [-v]
# 설치/자동 실행 (Pi, 사용자 단위라 sudo 불필요)
deploy/install.sh                        # systemd 사용자 서비스 + XDG autostart + labwc rc.xml
systemctl --user restart roaster-adapter
journalctl --user -u roaster-adapter -f
# Artisan 설정 파일 생성 (이 PC)
python3 tools/make_artisan_settings.py [--host <Pi IP>] [--port 8080]   # -> artisan/skywalker-rpi-websocket.aset
```

- 자동 실행: 데스크톱이 뜨면 `~/.config/autostart/roaster-adapter.desktop`(lxsession-xdg-autostart가 실행)이 사용자 서비스 `roaster-adapter.service`를 시작한다(`Restart=on-failure`). `~/.config/labwc/autostart`는 쓰지 않는다. labwc `-m`에서 시스템 autostart와 합쳐지는지 확인되지 않았기 때문이다. `tools/dev-run.sh`는 시작할 때 이 서비스를 멈춘다(포트 8080 충돌).

- 원격 셸에서 `pkill -f`를 쓸 때는 패턴이 그 ssh 명령 줄 자체와 겹치지 않게 한다. 겹치면 세션이 끊긴다. `tools/dev-run.sh`가 이 문제를 피하는 용도다.
- 스레드 경계: `arduino.ArduinoLink`만 별도 스레드(pyserial이 blocking)이고, 콜백은 `loop.call_soon_threadsafe`로 asyncio 루프에 넘긴다. 나머지(`controller`, `preheat`, `wsserver`, `ui`)는 모두 한 asyncio 루프에서 돈다.
- 규칙은 전부 `controller.Controller`에 있다(`_allowed()`가 출처별 권한, `check_watchdog()`가 워치독). UI와 WebSocket은 출처('touch', 'artisan')를 붙여 Controller 메서드를 부르기만 한다.
- `tools/fake_arduino.py`는 pty 위에서 SkyCommand의 루프 타이밍과 `readString()` 동작을 흉내 낸다. 명령 두 개가 한 번에 읽히면 `LOST`를 찍으므로 링크 타이밍 검증에 쓴다.
- LCD 설정: `/boot/firmware/config.txt`에 `dtoverlay=piscreen,drm`(ILI9486 DRM + ADS7846 터치). 터치 보정은 바탕화면의 "Touch Calibration"(`/usr/local/sbin/touch-calibrate`, tslib → udev `LIBINPUT_CALIBRATION_MATRIX`). labwc 설정은 `deploy/labwc-rc.xml`(= Pi의 `~/.config/labwc/rc.xml`)이며, UI 창(app_id `roaster-adapter`)을 SPI-1으로 옮겨 전체화면으로 만든다.

## 표시 온도

Artisan 소스를 확인한 결과(`canvas.py`의 `inputFilter`, `updateLCDs`), 기본 설정(`dropDuplicates`, `minmaxLimits`, `dropSpikes`가 꺼져 있고 `ETfunction`/`BTfunction`이 비어 있음)에서는 Artisan의 BT/ET LCD가 장치에서 받은 값을 필터 없이 `'%.1f'`로 보여 준다. `curvefilter`와 `filterDropOuts`는 RoR과 기록 종료 후 곡선에만 쓰인다. 그래서 라즈베리파이 LCD는 마지막으로 `getData`에 응답한 값을 같은 형식으로 보여 준다(Artisan이 연결되지 않았으면 최신 Arduino 값). 새 Artisan 설정에서 위 필터를 켜면 이 전제가 깨진다.

## Artisan ↔ 라즈베리파이: WebSocket

Modbus TCP와 MQTT도 Artisan이 지원하지만 쓰지 않는다. 두 방식 모두 라즈베리파이가 Artisan에 CHARGE나 DROP 이벤트를 먼저 보낼 수 없기 때문이다. Artisan의 WebSocket 장치(Device id 111)는 서버가 보낸 이벤트를 받아서 기록한다. 아래 내용은 Artisan 소스 `src/artisanlib/wsport.py`, `comm.py`(`WSread`), `main.py`(`eventaction` action 22)를 기준으로 했다.

- 라즈베리파이가 WebSocket **서버**이고, Artisan이 `ws://<host>:<port>/<path>`로 접속하는 클라이언트다.
- 메시지는 JSON 텍스트이고, 한 프레임에 여러 줄(`\n`으로 구분)을 넣을 수 있다.
- Artisan `[WebSocket]` 설정의 키 이름은 Artisan 기본값을 그대로 쓴다: `id_node=id`, `machine_node=roasterID`, `command_node=command`, `data_node=data`, `pushMessage_node=pushMessage`, `request_data_command=getData`, `charge_message=startRoasting`, `drop_message=endRoasting`, `addEvent_message=addEvent`, `event_node=event`.

### 온도 요청 (Artisan → 라즈베리파이)

```
요청: {"command":"getData","id":12345,"roasterID":0}
응답: {"id":12345,"data":{"BT":201.5,"ET":201.5}}
```

- Artisan은 샘플링 주기마다 이 요청을 보낸다.
- 응답에는 요청의 `id`를 그대로 넣어야 한다. `request_timeout`(기본 0.5초) 안에 응답이 없으면 그 샘플은 버려진다. 그래서 라즈베리파이는 Arduino에 바로 묻지 않고, 캐시해 둔 최신 값으로 즉시 응답한다.
- 채널 설정: 1번 채널이 BT, 2번 채널이 ET다(`WSread()`가 `readings[1], readings[0]`을 ET, BT 순으로 반환). `channel_nodes`는 `BT, ET`, `channel_modes`는 1(°C)로 한다. `channel_modes` 값은 0이 온도 아님, 1이 °C, 2가 °F다.
- ET 값은 BT를 복사해서 보낸다. 로스터에 온도 프로브가 하나뿐이기 때문이다.

### 제어 명령 (Artisan → 라즈베리파이)

Artisan 버튼과 슬라이더의 동작을 "WebSocket Command"로 설정하고 `send(<dict>)`를 쓴다. Artisan은 응답을 기다리지 않는다(`block=False`).

| 명령 JSON | Arduino 명령 |
|---|---|
| `{"command":"setHeater","value":n}` | `OT1;n` (0–100, 5 단위로 반올림) |
| `{"command":"setFan","value":n}` | `OT2;n` (0–100, 5 단위로 반올림) |
| `{"command":"setDrum","value":0\|1}` | `DRUM;0` / `DRUM;100` |
| `{"command":"setCooling","value":0\|1}` | `COOL;0` / `COOL;100` |
| `{"command":"setFilter","value":n}` | `FILTER;n` (0–4) |
| `{"command":"estop"}` | `ESTOP` |
| `{"command":"off"}` | `OFF` |
| `{"command":"charge"}` / `{"command":"drop"}` | 없음. Artisan에서 CHARGE/DROP을 눌렀다는 것을 LCD에 알리는 용도 |

- ESTOP은 Artisan의 `estop` 명령과 LCD의 ESTOP 버튼 둘 다 받는다. 예열 중에만 LCD 버튼으로 제한된다(아래 "예열" 절).
- 슬라이더 값은 float로 들어온다(예: `55.0`). 라즈베리파이에서 정수로 바꾼다.
- Artisan 쪽 명령 문자열은 `send(dict(command='setHeater',value={}))` 형태로 쓴다(이유는 "Artisan 설정 파일" 절). Artisan의 처리 과정(`str.format` → `;` 분리 → `eval`)을 흉내 내서, 이 문자열이 위 JSON으로 나가는 것을 확인했다. 실제 Artisan에서는 아직 시험하지 않았다.

### 이벤트 알림 (라즈베리파이 → Artisan)

```
{"pushMessage":"startRoasting"}                                    → CHARGE
{"pushMessage":"endRoasting"}                                      → DROP
{"pushMessage":"addEvent","data":{"event":"colorChangeEvent"}}     → DRY END
  (event 값: firstCrackBeginningEvent, firstCrackEndEvent, secondCrackBeginningEvent, secondCrackEndEvent)
```

- CHARGE: Artisan 설정에서 `STARTonCHARGE=true`면, 기록 중이 아닐 때 기록을 시작한 뒤 CHARGE를 찍는다. 이미 CHARGE가 찍혀 있으면 무시한다.
- DROP과 addEvent: 기록 중일 때만 반영된다. 이미 찍힌 이벤트는 다시 찍히지 않는다. `OFFonDROP=true`면 DROP 뒤에 기록을 멈춘다.
- **DROP(배출)** 은 출처와 상관없이(LCD 버튼이든 Artisan의 `drop` 명령이든) `OT1;0`, `OT2;80`, `COOL;100`을 보낸다(project.md). LCD에서 눌렀을 때만 Artisan에 `endRoasting`을 보낸다. Artisan에서 온 `charge`/`drop`은 되돌려 보내지 않는다.

### 워치독 (Artisan 연결 감시)

- 라즈베리파이는 Arduino에 `READ`를 계속 보낸다. 그래서 Arduino 자체의 10초 워치독은 Artisan이 끊겨도 동작하지 않는다. 대신 라즈베리파이가 이 역할을 한다.
- **`getData` 요청이 10초 동안 없으면, 라즈베리파이가 Arduino에 `OFF`를 보내 로스터를 멈춘다.** Arduino 워치독의 `shutdown()`과 같은 동작이다. LCD에는 경고를 표시한다.
- Artisan이 다시 연결돼도 출력을 자동으로 되돌리지 않는다.
- 그 결과, Artisan이 연결되어 있지 않으면 터치 UI만으로 로스터를 계속 돌릴 수 없다. 예외는 예열이다(아래 절). 구현에서는 Artisan이 `getData`를 보내지 않는 동안 LCD의 HEAT/FAN/DRUM/CHARGE/DROP을 비활성화한다(E-STOP과 PREHEAT만 동작).
- Arduino와 (재)연결되면 라즈베리파이가 `OFF`를 보내고 출력 상태를 0으로 맞춘다. 이전 상태를 알 수 없기 때문이다. 프로그램이 종료될 때도 `OFF`를 보낸다.

## 예열

순서의 원문은 `project.md`에 있다. 라즈베리파이가 혼자 진행하는 상태 머신이다.

| 단계 | 동작 | 다음 단계로 가는 조건 |
|---|---|---|
| 1 | Arduino에서 유효한 `READ` 응답을 받는지 확인한다 | 응답 확인. 실패하면 예열을 시작하지 않는다 |
| 2–3 | `DRUM;0`, `OT1;80`, `OT2;10` | 즉시 |
| 4 | 가열 1 | 온도 180 °C 도달 |
| 5 | `OT1;0`, `OT2;0` | 5분 경과 |
| 6 | `OT1;75`, `OT2;20`, `DRUM;100` | 즉시 |
| 7 | 가열 2 | 온도 180 °C 도달 |
| 8 | `OT1;0`, `OT2;0`, `DRUM;0` | 5분 경과 |
| 9 | 예열 종료를 LCD에 표시한다. 모든 출력은 꺼진 상태다 | 종료 |

- **예열 중에는 라즈베리파이 LCD의 ESTOP 버튼만 동작한다.**
  - Artisan 워치독(`getData` 10초 감시)은 동작하지 않는다.
  - WebSocket 제어 명령은 `estop`까지 포함해 모두 무시한다. `getData`에는 계속 응답해서 Artisan이 온도를 볼 수 있게 한다.
  - LCD 터치도 ESTOP 버튼을 빼고는 모두 무시한다.
- LCD ESTOP 버튼을 누르면 Arduino에 `ESTOP`(히터 0, 팬 100)을 보내고 예열을 끝낸다.
- 예열이 끝나면(정상 종료든 ESTOP이든) Artisan 워치독이 다시 동작한다. 10초는 예열이 끝난 시점부터 센다.
- **기본값으로 정한 것 (project.md에 없음, 바꿀 수 있음):**
  - 온도 단위는 °C다.
  - 도달 판정은 Arduino 온도가 3회 연속 180 °C 이상일 때로 한다.
  - 가열 단계(4, 7)가 15분 안에 끝나지 않으면 `OFF`를 보내고 예열을 중단한다.
  - Arduino의 유효한 온도 응답이 5초 넘게 없으면 `OFF`를 보내고 예열을 중단한다.
  - 예열을 시작하는 방법은 LCD 터치 버튼뿐이다.

## `SkywalkerRoaster/`는 참고용, 수정 금지

`SkywalkerRoaster/`는 upstream `jmoore52/SkywalkerRoaster`를 가리키는 git 서브모듈이다(`git clone --recurse-submodules`, 또는 `git submodule update --init`). 참고 자료로만 두며 수정하지 않는다. `tools/make_artisan_settings.py`가 이 안의 `.aset`을 템플릿으로 쓰므로 서브모듈이 있어야 한다. Arduino에는 `SkyCommand/SkyCommand.ino`를 그대로 올려 쓰고, 라즈베리파이 프로그램이 이 펌웨어의 동작에 맞춘다. 배선과 로스터 비트뱅 프로토콜은 `SkywalkerRoaster/README.md`에 정리되어 있다.

## 라즈베리파이가 상대하는 Arduino 인터페이스 (`SkyCommand.ino`)

- USB 시리얼 115200 baud, 8N1. Arduino는 TC4 장치처럼 동작한다.
- 명령 형식은 `CMD` 또는 `CMD;value`이다.

| 명령 | 동작 |
|---|---|
| `READ` | 응답 `0.0,<temp>,<temp>,<heat>,<vent>,0` (`<temp>` 두 개는 같은 값) |
| `OT1;n` | 히터 듀티 0–100 |
| `OT2;n` | 팬(배기) 듀티 0–100 |
| `DRUM;n` | 0이면 드럼 정지, 그 외는 드럼 100 |
| `COOL;n` | 원두 냉각 팬 |
| `FILTER;n` | 필터(박스 냉각) 팬 |
| `OFF` | 모든 출력 0 |
| `ESTOP` | 히터 0, 팬 100 |
| `CHAN` | 응답 `# Active channels set to 0200` |
| `UNITS;C` / `UNITS;F` | 온도 단위 (기본값 F) |

- `<temp>`는 로스터의 ADC 값 두 개로 계산한 4차 다항식 결과이고, 기본 단위는 °F이다. Arduino는 항상 °F로 두고 `UNITS` 명령은 보내지 않는다. °C 변환은 라즈베리파이가 한다. 이렇게 하면 Arduino가 리셋돼도 단위를 다시 설정할 필요가 없다.
- 로스터는 팬·히터 듀티가 5의 배수일 때만 반영하는데, 펌웨어는 이를 강제하지 않는다.
- **Arduino의 갱신 속도:** `loop()` 한 바퀴가 온도를 한 번 읽는다. 아래는 코드에 적힌 지연 시간으로 계산한 값이고, 실제 하드웨어에서 측정한 것은 아니다.
  - 로스터로 제어 프레임 전송: 약 80–120 ms.
  - 로스터 프리앰블 대기와 56비트 수신: 약 100–250 ms. 체크섬 실패나 타임아웃이 나면 최대 500 ms까지 걸리고, 이전 온도가 그대로 남는다.
  - 시리얼 입력이 있으면 `Serial.readString()`의 100 ms 타임아웃이 더해진다.
  - 합치면 한 바퀴에 약 0.25–0.35초, 즉 **초당 약 3–4회** 온도를 갱신한다.
- **명령은 하나씩, 간격을 두고 보내야 한다.** 시리얼을 `readString()`으로 한 번에 읽고 첫 `;`로만 나누기 때문에, 두 명령이 한 번에 읽히면(예: `READ\nOT1;50`) 둘 다 무시된다. 라즈베리파이는 Artisan과 터치 UI의 명령을 큐 하나로 모아서 보낸다. `READ` 폴링은 Arduino 루프 주기보다 느리게 보낸다(예: 0.5초 간격).
- **10초 워치독:** Arduino는 10초 동안 아무 명령도 받지 못하면 `shutdown()`으로 모든 출력을 끈다. 온도가 300 °C를 넘으면 `eStop()`을 실행한다.
- 로스터는 약 1초 동안 제어 프레임을 받지 못하면 꺼진다. 신호선이 끊기거나 Arduino가 빠지면 드럼과 팬까지 즉시 멈추므로, 로스팅 중에는 화재 위험이 있다.

## Artisan 설정 파일 (`artisan/skywalker-rpi-websocket.aset`)

`tools/make_artisan_settings.py`가 `basic-skitop-artisan-settings.aset`을 복사해서 필요한 키만 바꾼다. 손으로 고치지 말고 스크립트를 고친 뒤 다시 생성한다.
- 장치를 WebSocket(`id=111`)으로 바꾸고, `[WebSocket]`에 host/port/path, `STARTonCHARGE=true`, `channel_nodes=BT, ET`, `channel_modes=1, 1`(°C)을 넣는다. 샘플링은 `Delay=1000`이다. ET 곡선과 LCD는 숨긴다(BT 복사본이기 때문).
- "WebSocket Command"는 저장 위치마다 번호가 다르다. 기본 이벤트 버튼과 ON/OFF 버튼은 21, 추가 이벤트 버튼은 22, 슬라이더는 18이다. Artisan `main.py`의 `eventactionx()`, `fireslideraction_internal()`, `recordextraevent()`가 각각 다르게 내부 번호 22로 바꾸기 때문이다.
- 명령 문자열은 `send(dict(command='setHeater',value={}))` 형태로 쓴다. 추가 버튼과 슬라이더 문자열에는 Artisan이 `str.format()`을 적용하므로 JSON 리터럴의 `{`가 깨진다. `_`, `$`, `;`, `#`도 Artisan이 특별하게 처리하므로 명령에 넣지 않는다.
- `Mode=F`는 템플릿 그대로 둔다. °C로 쓰려면 Artisan에서 Config > Temperature > Celsius Mode로 바꾼다. 이 메뉴를 쓰면 Artisan이 축, 단계 등 온도 설정을 함께 변환한다.

## Artisan 설정에서 참고할 값 (`ArtisanConfigs/basic-skitop-artisan-settings.aset`)

`.aset`는 Qt INI 형식이다. 바이너리 `@Variant(...)` 값이 섞여 있어서 grep할 때는 `grep -a`를 쓴다. 참고 설정은 TC4 시리얼 장치용이라, 새 설정에서는 장치를 WebSocket으로 바꾸고 시리얼 명령을 위의 `send(...)` 명령으로 옮긴다.

- **장치:** `[Device] id=19` (Arduino TC4), `arduinoBTChannel=1`, `arduinoETChannel=None`. `[SerialPort]`은 115200 / 8N1 / `timeout=0.8`이다.
- **샘플링 주기:** `Delay`가 basic과 perf-beta 설정은 250 ms, 나머지 두 설정은 2000 ms다. Artisan 기본값은 1000 ms다.
- **필터 설정:** `Mode=F`, `curvefilter=3`, `filterDropOuts=true`, `dropSpikes=false`, `minmaxLimits=false`, `deltafilter=7`, `optimalSmoothing=false`, `ETfunction`/`BTfunction` 비어 있음. 이 조합에서는 LCD 값에 필터가 걸리지 않는다("표시 온도" 절). 새 설정은 `Mode=C`로 한다.
- **슬라이더 `[Sliders]`:** 1번 슬라이더는 `OT2;{}`(팬), 4번 슬라이더는 `OT1;{}`(히터)이다. `slideractions=1, 0, 0, 1`, 범위는 0–100이다.
- **기본 이벤트 버튼 `[DefaultButtons]`:**
  - `buttonactionstrings`의 8칸은 CHARGE, DRY END, FCs, FCe, SCs, SCe, DROP, COOL END 순서다.
  - DROP에는 `COOL;100`, COOL END에는 `COOL;0`이 들어 있다.
  - 실제로 실행할지는 같은 위치의 `buttonactions` 값이 정한다. basic 설정은 전부 0이고, `sliders-buttons-mathwiz` 설정은 DROP과 COOL END가 1(시리얼 명령)이다. 내부 액션 번호 목록은 Artisan `main.py`의 `eventaction()` 주석에 있다(22 = WebSocket Command). 다만 설정 파일에 저장되는 번호는 `eventactionx()`와 슬라이더 쪽 코드에서 다시 매핑되므로, 그대로 같다고 가정하지 말고 Artisan에서 설정을 저장해 확인한다.
- **추가 버튼 `[ExtraEventButtons]`:** `extraeventsactionstrings`에 `DRUM;100`, `DRUM;0`, `COOL;100`, `COOL;0`, `FILTER;1`, `FILTER;0`, `OFF`가 들어 있다. perf-beta 설정에는 `ESTOP`도 있다.
- 다른 `.aset` 파일 세 개는 이 설정을 변형한 것이다. 버튼 수, ET/BT 채널(`arduinoETChannel=1`, `arduinoBTChannel=2`), PID 버튼 사용 여부가 다르다.
