# remote-controller-minimal

학습용 최소 구성: FE(Nginx), BE(FastAPI), DB(MariaDB), Python 에이전트.
FE는 BE 조회와 화면 표시만 담당한다. 에이전트는 BE에 직접 POST한다.

## 서버 실행

Docker Desktop을 시작한 뒤 저장소 폴더에서:

```powershell
docker compose up --build -d
```

- 화면: http://localhost:8080 (다른 PC에서는 localhost 대신 중앙 PC의 LAN IP)
- API 문서: http://localhost:8000/docs
- 중앙 PC 방화벽에서 필요한 내부망에 TCP 8080, 8000 접근을 허용한다.
- DB는 외부 포트를 공개하지 않는다. 데이터는 db-data 볼륨에 남는다.
- 중지: `docker compose down`

## 에이전트 실행

다른 Windows PC 5대에 Python 3.12 이상과 agent.py만 복사한 뒤 실행한다.
CPU·메모리 사용률 수집용 psutil을 한 번 설치한다.

```powershell
python -m pip install psutil
python agent.py http://중앙PC의LAN주소:8000
```

ID는 실행 시 {장치명}-{MAC 주소 끝 6자리}로 결정한다.
예: 장치명 DESKTOP-01, MAC AA:BB:CC:DD:EE:FF → DESKTOP-01-DDEEFF.
MAC 구분자는 제거하고 6자리는 대문자로 사용한다. AGENT_MAC 설정도 ID 생성에 반영한다.
장치명·MAC이 같으면 재실행해도 같은 ID이며, 둘 중 하나가 바뀌면 ID도 바뀐다.
기존 .agent-id 파일은 더 이상 읽거나 쓰지 않으므로 남아 있어도 무시한다. Ctrl+C로 종료한다.

에이전트는 시작할 때 장비를 등록하고, 정상 통신 시 1초마다 사용 상태와 시스템 전체 CPU·메모리 사용률(%)을 함께 보고한다.
CPU는 직전 측정 이후 사용률, MEM은 물리 메모리 사용률이다. 첫 보고 전 약 1초간 CPU 측정 기준을 준비한다.
요청이 지연되면 실제 보고 간격도 늘어난다. 통신 실패 시 다음 주기에 재등록한다.
IP 변경은 에이전트를 재시작해 반영한다.

IP는 서버로 가는 LAN 경로에서 선택하고 MAC은 uuid.getnode()로 얻는다.
다중 NIC 환경에서 MAC이 해당 LAN NIC와 다를 수 있으므로 필요하면 실행 전에 지정한다:

```powershell
$env:AGENT_IP = "192.168.0.21"
$env:AGENT_MAC = "AA:BB:CC:DD:EE:FF"
$env:AGENT_WS_PORT = "8765"
```

## 저장과 상태

- MariaDB: agent_id(VARCHAR(262), 기본키), 장치명, MAC, IP, 예약된 WebSocket 포트만 저장.
- BE 메모리: 최신 사용 상태, CPU·메모리 사용률, 마지막 입력 이후 경과 시간과 수신 시각. 이력은 저장하지 않음.
- FE: 1초마다 BE 조회. CPU·MEM 사용률과 마지막 동작(초·분·시간 전)을 표시하며 최근 보고 열은 없다.
  마지막 동작은 보고 시점의 키보드·마우스 입력 유휴 시간(idle_seconds)을 초·분·시간 단위로 내림하여 표시한다(10000초 → 2시간 전).
  마지막 보고에서 5초가 지나면 연결 끊김과 사용률·마지막 동작 — 표시.
  이전 버전 에이전트에서 사용률이나 마지막 동작을 보내지 않으면 해당 항목은 — 표시.
- BE 재시작 후 장비 정보는 남고, 다음 보고 전까지 확인 중 표시.
- ctypes로 Windows GetLastInputInfo를 호출해 마지막 키보드·마우스 입력 이후 시간을 확인한다.
  디버깅용 기준: 10초 미만이면 사용중, 10초 이상이면 부재중. agent.py의 IDLE_SECONDS로 변경한다.
  키 내용·마우스 좌표는 수집하지 않는다. 로그인한 사용자 세션에서 실행해야 한다.
  잠금 상태는 별도로 판단하지 않으며, 입력 시각 조회 실패 시 잘못된 상태를 보고하지 않고 재시도한다.
- 왼쪽 전원 버튼은 BE의 POST /api/agents/{id}/wake를 호출한다.
  BE가 DB의 MAC으로 매직 패킷(FF 6바이트 + MAC 16회)을 UDP 255.255.255.255:9에 전송한다.
  브로드캐스트 주소는 BE 환경변수 WOL_BROADCAST로 변경할 수 있다.
  전송 성공은 실제 부팅 확인이 아니며, PC의 BIOS·NIC에서 WoL이 활성화되어 있어야 한다.
  Docker에서 실제 LAN으로의 패킷 전달과 다른 서브넷 중계는 이번 구현 범위에 포함하지 않는다.
- WebSocket, 원격 실행, 자동 시작, 종료 알림은 다음 단계.
  현재 등록하는 ws_port는 예약 정보이며 수신 포트를 열지 않는다.
- BE는 메모리를 사용하므로 Uvicorn worker 하나로 실행.

## 파일

- be.py: 장비 등록, 상태 수신, 조회 API와 DB 초기화.
- index.html: HTML/CSS/JavaScript가 들어 있는 단일 화면 파일.
- agent.py: 등록, CPU·메모리 수집, 입력 유휴 시간에 따른 상태 보고.
- compose.yaml / Dockerfile / requirements.txt: 서버 구성과 의존성.

별도 프록시, 프런트엔드 프레임워크, ORM은 사용하지 않는다.
현재는 인증 없는 HTTP 학습용 예제와 공개된 연습용 DB 암호를 사용한다.
접근을 실습용 내부망으로 제한하고, 인증·HTTPS 추가 전에는 인터넷에 공개하지 않는다.