# fromKS: Tizen KS → 패키지 리스트/다운로더 (원리 설명서)

이 문서는 `download.py`/`download_debug-rpms_from_ks.py`(동일 계열) 프로그램이 **Tizen KS(Kickstart) 스크립트**를 읽고, **패키지/의존성 해석**을 거쳐, **베이스 RPM / 디버그(-debuginfo / -debugsource)** 를 **Tizen 리포**에서 내려받는 전체 원리를 자세히 설명합니다.

---

## 핵심 목표

- **이미지는 실제로 생성하지 않음.** KS에서 **필요 패키지만** 뽑고, 원하면 해당 리포에서 RPM만 받음.
- **리눅스 공용 메타데이터 서버 사용 X.** 오직 **사용자가 제공한 Tizen 리포**의 `repodata`만 사용.
- **KS의 프리셋/그룹 토큰**(예: `building-blocks-root-Preset_*`)도 **comps(group) 메타**로 확장해 **실제 패키지 명**으로 변환.
- **디버그 전용 모드 지원.** 해석은 packages 메타로 하고, 다운로드는 debug 리포에서 `-debuginfo` 중심으로 수행.  
  (`-debugsource`는 기본 **끄기**, config/CLI로만 **켜기**)
- **병렬 다운로드 및 메타데이터 파싱 지원 (`--parallel`)**
- **HTTP 타임아웃(`--timeout`)과 재시도(`--retries`) 설정 가능**
- **성공적으로 다운로드된 파일과 URL을 CSV(`--csv-out`)로 기록**

---

## 큰 그림
```
        ┌─────────────┐
        │   KS(.ks)   │  <-- %include, %ifarch 등 처리
        └─────┬───────┘
              │           (1) KS 파싱
              ▼
      ┌──────────────┐
      │  패키지 시드 │  <-- include/exclude, @group(토큰)
      └──────┬───────┘
             │           (2) 그룹(comps) 확장
             ▼
  ┌────────────────────┐
  │   실제 패키지 목록 │
  └─────────┬──────────┘
            │           (3) 의존성 해석
            ▼
    ┌──────────────┐
    │  의존성 클로저│  <-- provides/requires로 계산
    └──────┬───────┘
           │           (4) 다운로드(옵션)
           │
   ┌───────▼────────┐
   │ base / debug    │  <-- mode: base|debug|both
   └─────────────────┘
```

---

## KS 파서(1): 뭘 읽고, 어떻게 읽나

- **입력**: URL 또는 로컬 파일
- **지원**:
  - `%include <path>`: **재귀 포함** (상대경로는 KS URL 기준으로 해석)
  - `%ifarch aarch64 x86_64` / `%if 1` / `%else` / `%endif` : **간단 조건 분기**
  - `%packages ... %end` 블록:  
    - 일반 패키지명  
    - `-패키지명`(exclude)  
    - `@그룹`(group 토큰)  
- **결과**:  
  - `includes`: 포함할 패키지/토큰 모음  
  - `excludes`: 제외 목록  
  - `groups`: `@그룹` 토큰들  
  - `sources`: 파싱한 KS 파일 목록(루트 + include)

> 📝 줄 끝의 `\`로 이어쓰기를 허용하고, `#` 이후는 주석으로 제거합니다.

---

## 그룹 확장(2): 프리셋/그룹 토큰 → 실제 패키지

- **왜 필요?** 스냅샷 KS에는 실제 패키지 대신 **그룹/프리셋 ID**가 들어있는 경우가 많습니다.
- **어떻게?**
  1. `repodata/repomd.xml`에서 `type="group"`(또는 `group_gz`) 항목 찾기
  2. **comps XML**을 가져와 `<group><id>...</id> ... <packagereq type="mandatory|default">name</packagereq>`들을 **실제 이름**으로 추출
  3. KS에서 발견된 토큰(`building-blocks-*` 등)이 **comps의 group id**와 일치하면, 그 그룹에 속한 **패키지 리스트로 치환**

> 결과적으로 KS의 **토큰 seed** → **실제 패키지 seed**로 변환됩니다.

---

## 리포 인덱싱(3): 의존성 해석을 위한 메타 읽기

- **입력**: 사용자 제공 `repos[]` (packages / debug 경로 아무거나 가능)
- **자동 짝(pair) 유도**:
  - 입력이 `.../packages/`면 **동일 스냅샷의** `.../debug/`를 **추정** (반대도 마찬가지)
  - 이유:  
    - 해석은 **packages 쪽 `primary.xml`**로 해야 안정적  
    - 다운로드는 모드에 따라 **packages**(베이스) 또는 **debug**(디버그)에서
- **repomd.xml → primary.xml(.gz)**:
  - `repodata/repomd.xml`에서 `type="primary"` 엔트리의 `href`를 찾아 **절대 URL** 구성
  - `primary.xml`에서 **모든 패키지**를 읽어:
    - `name`, `arch`, `href`, `provides{}`, `requires{}`
- **네임스페이스(중요)**: `http://linux.duke.edu/...`  
  - 이건 **네트워크 주소가 아니라 XML 스키마 식별자**입니다.  
  - Tizen도 **RPM-MD 포맷**을 그대로 쓰므로, 네임스페이스는 **그대로**여야 파싱이 됩니다.

---

## 의존성 해석(3-2): provides/requires로 클로저 만들기

- **큐 기반**(BFS에 가까운 단순 확장)
  1. seed 패키지(그룹 확장된 것 포함)를 **이름→메타**로 픽업(arch 우선: `aarch64` → `noarch` → 아무거나)
  2. 각 패키지의 `requires` 능력(capability)을 `provides`에서 **제공자**로 매핑
  3. 아직 방문 안 한 패키지를 큐에 추가
- **결과**: `visited_pkgs`가 **해석된 클로저**(패키지 집합)
- **주의**: 리포 조합(스냅샷 혼합 등)에 따라 **미해결 capability**가 남을 수 있으며, 이건 WARN으로 요약 출력

---

## 다운로드(4): mode에 따라 base/debug/both

- `--mode` 또는 config `"mode"`:
  - `base` : **베이스 RPM**만 (`packages`에서)
  - `debug`: **디버그 RPM**만 (`debug`에서 `-debuginfo` 중심, `-debugsource`는 기본 제외)
  - `both` : 둘 다
- **`-debugsource` 기본 꺼짐**  
  - `--with-debugsource` 또는 config `"with_debugsource": true`일 때만 추가
- **경로 조합 이슈 대응 (중요)**  
  - 어떤 스냅샷에서는 **debug 리포가 `/debug/` 루트 바로 아래에 파일**을 두기도 합니다.
  - 반면 `primary.xml`의 `href`는 `aarch64/<파일>`처럼 **아키텍처 접두**가 붙기도 함.
  - 그래서 URL은 아래 **후보(fallback)** 를 순차시도:
    1) `repo_base` + `href` (표준)
    2) `/debug/` 리포인데 `href`가 `aarch64/...`로 시작 → **접두 제거**해 `/debug/<파일>`
    3) `repo_base`가 `/debug/aarch64`로 끝나는데 `href`가 파일명만 → **부모 `/debug/`로 올려** `/debug/<파일>`
  - 후보마다 받아보기 → 성공 시 종료 / 실패 시 다음 후보

---

## 병렬 처리 & CSV 출력

- `--parallel` 옵션으로 다운로드 및 메타데이터 파싱 시 워커 수를 조절할 수 있습니다.  
  기본값은 CPU 코어 수의 2배이며, 최소 4, 최대 16까지 설정 가능합니다.
- `--timeout` 옵션으로 HTTP 요청 타임아웃(초)을 지정할 수 있으며, 기본값은 30초입니다.
- `--retries` 옵션으로 실패 시 재시도 횟수를 지정할 수 있으며, 기본값은 2회입니다.
- `--csv-out` 또는 설정 파일의 `"csv_out"` 키를 사용하면, 성공적으로 다운로드된 파일 경로와 실제 URL 쌍을 CSV 파일로 저장합니다.
- CSV 파일 예시:
  ```
  file,url
  ./rpms-base-UplusB-snapshot/package1.rpm,https://download.tizen.org/snapshots/.../package1.rpm
  ./rpms-base-UplusB-snapshot/package2.rpm,https://download.tizen.org/snapshots/.../package2.rpm
  ```

---

## 설정 파일(JSON) 예시

> **요청 사항대로**: ① 기본(베이스만) ② 디버그만 ③ 둘 다  
> `with_debugsource`는 **항상 false**(기본값)  
> 병렬, 타임아웃, 재시도, CSV 출력 옵션이 추가됨

### 1) `basic.json` — 베이스만
```json
{
  "ks": "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/builddata/images/standard/image-configurations/tizen-headless-aarch64.ks",
  "repos": [
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base/tizen-base_20250805.212546/repos/standard/packages/",
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/repos/standard/packages/aarch64/"
  ],
  "arch": "aarch64",
  "mode": "base",
  "derive_pairs": true,
  "out": "./rpms-base-UplusB-snapshot",
  "format": "markdown",
  "show_groups": true,
  "download": true,
  "with_debugsource": false,
  "parallel": 12,
  "timeout": 30,
  "retries": 2,
  "csv_out": "./rpms-base-UplusB-snapshot.csv"
}
```

### 2) `debug.json` — 디버그만(`-debuginfo`)
```json
{
  "ks": "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/builddata/images/standard/image-configurations/tizen-headless-aarch64.ks",
  "repos": [
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base/tizen-base_20250805.212546/repos/standard/packages/",
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/repos/standard/packages/aarch64/"
  ],
  "arch": "aarch64",
  "mode": "debug",
  "with_debugsource": false,
  "derive_pairs": true,
  "out": "./rpms-debug-UplusB-snapshot",
  "format": "markdown",
  "show_groups": true,
  "download": true,
  "parallel": 12,
  "timeout": 30,
  "retries": 2,
  "csv_out": "./rpms-debug-UplusB-snapshot.csv"
}
```

### 3) `both.json` — 베이스 + 디버그
```json
{
  "ks": "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/builddata/images/standard/image-configurations/tizen-headless-aarch64.ks",
  "repos": [
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base/tizen-base_20250805.212546/repos/standard/packages/",
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/repos/standard/packages/aarch64/"
  ],
  "arch": "aarch64",
  "mode": "both",
  "with_debugsource": false,
  "derive_pairs": true,
  "out": "./rpms-both-UplusB-snapshot",
  "format": "markdown",
  "show_groups": true,
  "download": true,
  "parallel": 12,
  "timeout": 30,
  "retries": 2,
  "csv_out": "./rpms-both-UplusB-snapshot.csv"
}
```

---

## 실행 예

```bash
# 1) 베이스만
python3 ./download_debug-rpms_from_ks.py --config ./basic.json

# 2) 디버그만 (-debuginfo)
python3 ./download_debug-rpms_from_ks.py --config ./debug.json

# 3) 둘 다
python3 ./download_debug-rpms_from_ks.py --config ./both.json

# 일시적으로 -debugsource까지 받고 싶다면 (기본은 false)
python3 ./download_debug-rpms_from_ks.py --config ./debug.json --with-debugsource

# 병렬 12, 타임아웃 20초, 재시도 3회, CSV 출력 지정 예
python3 ./download_debug-rpms_from_ks.py --config ./both.json --parallel 12 --timeout 20 --retries 3 --csv-out ./rpms-both-UplusB-snapshot.csv

# 설정 파일의 값이 기본이며, CLI 옵션이 우선 적용됩니다.
```

---

## 로그 읽는 법

- `Fetching group metadata:` … `group.xml[.gz]` → **그룹 확장**에 필요한 comps 로딩
- `Fetching primary metadata:` … `primary.xml[.gz]` → 의존성 해석에 쓰일 **패키지 인덱스** 로딩
- `Expanded N preset/group token(s)` → KS 토큰이 실제 패키지로 **확장되었음**
- `Downloading ... (base)` / `(debug)` → 실제 **파일 저장**
- `try 1/2` → **폴백 URL** 시도 중
- `Capabilities with no provider ...` → 현재 리포 조합으로는 **해결 불가한 requires** (리포/스냅샷을 보강해야 함)

---

## 자주 묻는 질문(FAQ)

**Q1. 왜 네임스페이스가 `linux.duke.edu` 인가요?**  
A. RPM-MD 포맷(XML)의 **스키마 식별자**입니다. **네트워크 요청이 아닙니다.** 여기 값이 바뀌면 XML 파서가 요소를 못 찾습니다.

**Q2. `repodata/repomd.xml`이 두 레벨로 섞여 있던데요?**  
A. Tizen은 `repodata/primary.xml.gz`의 `href`가 **리포 루트** 기준일 수 있습니다. 그래서 `repomd.xml`의 상위(부모)를 기준으로 **절대 URL**을 조합합니다.

**Q3. 왜 디버그 리포 URL이 자꾸 404 나요?**  
A. 스냅샷에 따라 debug 리포가 **`/debug/` 루트에 직접 파일을 둠**(아키 폴더 없음).  
   프로그램이 **후보 URL을 자동 생성**해 순차 시도합니다.

**Q4. KS에 실제 패키지명이 하나도 안 보이는데요?**  
A. 그게 정상일 수 있습니다. 대부분을 **그룹 토큰**으로 관리합니다. 이 도구가 comps로 **실제 목록으로 확장**합니다.

**Q5. CSV 출력 파일은 어떻게 생기나요?**  
A. 헤더 `file,url`로 각 다운로드된 RPM 경로와 실제 URL이 기록됩니다. 이미 존재하는 파일은 첫 후보 URL로 기록됩니다.

---

## 한계 & 팁

- **스냅샷 혼합**(예: Base=2025-08, Unified=2025-04): 그룹 구성/패키지 버전 차이로 일부 requires가 **미해결**될 수 있습니다.
- **속도**: 한 번 실행하면 메타를 많이 받습니다. 필요하면 메타 캐싱/병렬 다운로드를 추후 옵션으로 넣으세요.
- **보안**: 제공받은 URL만 접속합니다. 프록시/사내 미러 환경에서 사용시 `urllib` 레벨 프록시 변수로 제어하세요.

---

## 확장 아이디어

- **--save-manifest**: 해석된 패키지/버전 목록을 JSON/CSV로 저장
- **--parallel N**: 다운로드 병렬화
- **--only PATTERN**: 특정 패턴만 필터링해서 다운로드
- **–exclude-debugsource**(기본값)처럼 토글을 더 세분화 (예: `--only-debuginfo`)

---

## 결론

- KS → (그룹 확장) → 의존성 클로저 → (모드별) 베이스/디버그 다운로드
- 오직 **Tizen 리포 메타데이터**만 사용
- 스냅샷/리포 레이아웃 차이(특히 debug)까지 **폴백 URL**로 견고하게 대응
- `-debugsource`는 **기본 끔**, 필요할 때만 옵션으로