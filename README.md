# 🎬 boxoffice-viz

KOBIS(영화진흥위원회) 일일 박스오피스 데이터를 매일 수집해 누적하고,
인터랙티브 차드로 시각화한 정적 리포트를 GitHub Pages로 배포하는 미니
데이터 파이프라인 프로젝트입니다.

```
KOBIS API → 수집(fetch) → 누적 저장(data/*.csv) → pandas 분석
        → plotly 차트 + Jinja 템플릿 → index.html → GitHub Pages (매일 자동 갱신)
```

## 산출물

- **팩트 테이블** `data/boxoffice.csv` — 일자별 박스오피스(순위/관객수/누적)
- **차원 테이블** `data/movies.csv` — 영화 마스터(장르/국가/개봉일)
- **리포트** `index.html` — KPI 카드 + 일일 TOP10 / 누적 추이 / 장르·국가 비중

## 구조

```
boxoffice-viz/
├── fetch.py                  # KOBIS OpenAPI 수집 (일일박스오피스 + 영화상세)
├── pipeline.py               # 누적 저장(멱등) + 분석 + HTML 렌더링 + CLI
├── template.html             # Jinja 리포트 템플릿
├── data/                     # boxoffice.csv, movies.csv (자동 생성/커밋됨)
├── tests/test_pipeline.py    # 저장/분석 로직 검증 (네트워크 없음)
├── .github/workflows/daily.yml  # 매일 KST 09:00 실행 + 커밋
├── requirements.txt / requirements-dev.txt
└── pyproject.toml            # pytest pythonpath 설정
```

## 로컬 실행

```bash
# 1) 의존성
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # 테스트까지

# 2) KOBIS 키 (https://www.kobis.or.kr 에서 발급 후)
export KOBIS_KEY=발급받은키

# 3) (최초 1회) 최근 한달 백필로 히스토리 시딩 — 차트가 바로 풍성해짐
python pipeline.py --backfill $(gdate -d '1 month ago' +%Y%m%d) $(date +%Y%m%d)
#   ※ macOS GNU date 미사용 시: python pipeline.py --backfill 20240101 20240131

# 4) 일일 갱신 (KST 어제 1건)
python pipeline.py

# 5) 테스트
pytest
```

## GitHub 배포 (최초 1회 설정)

1. 이 저장소를 GitHub에 푸시한다.
2. **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `KOBIS_KEY` / Value: 발급받은 키
3. **Settings → Pages**
   - Source: `Deploy from a branch` / Branch: `main` / Folder: `/ (root)`
4. **Actions 탭**에서 `Daily box office update` 워크플로를 `Run workflow`로
   수동 1회 실행 → 이후 매일 KST 09:00에 자동 갱신된다.

배포 주소: `https://<계정>.github.io/boxoffice-viz/`

## 데이터 출처

[영화진흥위원회 KOBIS OpenAPI](https://www.kobis.or.kr/kobisopenapi/)
