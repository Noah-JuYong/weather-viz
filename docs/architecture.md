# Architecture

## Overview

weather-viz는 Open-Meteo의 관측·예보 데이터를 도시별 CSV에 누적하고,
Plotly와 Jinja로 정적 리포트를 생성해 GitHub Pages에 배포한다.

## Data flow

Open-Meteo → `data/*.csv` → pandas/Plotly → `site/*.html` → GitHub Pages

과거 관측 API 요청이 실패하면 기존 CSV를 덮어쓰지 않고 실행을 실패시킨다. 반면 예보 API
요청이 실패하면 오류를 기록하고 예보를 건너뛴 채, 기존 관측 데이터로 리포트를 생성해
배포한다. 분석과 렌더링 단계는 필요한 CSV 열이나 템플릿이 없으면 실패한다. 배포 단계는
생성한 `site/` 전체를 Pages 아티팩트로 업로드하며, 업로드나 배포에 실패하면 이전 Pages
배포본이 유지된다.

도시별 CSV는 이미 수집한 날짜를 다시 요청하지 않는 증분 방식으로 갱신한다. 이 방식은 API
호출량을 줄이고, 누적 관측 이력을 보존하며, 매일 실행해도 필요한 새 관측과 예보만 반영하게
한다.

## Repository boundaries

- `src/weather_viz/`: 수집과 리포트 생성 코드
- `data/`: Git에서 이력을 추적하는 공개 누적 데이터
- `site/`: 실행 때만 생성되는 Pages 아티팩트
- `tests/`: 네트워크 없이 실행되는 회귀 테스트

생성된 HTML은 Git에 추적하지 않는다. 소스 코드와 CSV에서 언제든 재생성할 수 있는 산출물이기
때문에 변경 이력의 잡음을 줄이고, Actions가 생성한 `site/`만 Pages 아티팩트로 배포한다.

## Automation

예약 또는 수동 Actions 실행이 데이터를 갱신하고, CSV만 커밋한 뒤
생성된 `site/`를 Pages 아티팩트로 배포한다.
