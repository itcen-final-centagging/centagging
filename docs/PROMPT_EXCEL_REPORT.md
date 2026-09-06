# 프롬프트 평가 통합 Excel 보고서

객체 탐지·속성 추출 평가 CSV와 XAI 평가 CSV를 하나의 Excel 문서로 합칩니다.

## 생성 명령

```powershell
docker compose exec -T api python -m app.evaluation.prompt_excel_report `
  --metrics-summary /app/uploads/evaluation/prompt_metrics_summary.csv `
  --version-comparison /app/uploads/evaluation/prompt_version_comparison.csv `
  --xai-results /app/uploads/evaluation/xai-batch-v1-v2.csv `
  --output /app/uploads/evaluation/prompt_evaluation_report.xlsx
```

## 시트 구성

- `종합 비교`: 세 프롬프트의 전체 지표와 v1·v2 우세 결과
- `공통 지표`: 정상 응답률과 평균·P95 처리 시간 비교
- `객체 탐지`: F1, IoU, 근거 언어, 토큰 효율 비교
- `속성 추출`: 속성 F1, 누락률, 카테고리 정확도 비교
- `XAI`: 응답 계약, 루브릭, 라벨, VLM mood 비교
- `원본 결과`: 보고서 생성에 사용한 CSV 원본

## 확인 순서

1. `종합 비교`에서 v2 우세·v1 우세·동률 지표 수를 확인합니다.
2. `공통 지표`에서 성공률이 유지되는지, 처리 시간이 개선됐는지 확인합니다.
3. 각 프롬프트 시트에서 품질 지표가 개선됐는지 확인합니다.
4. 결과가 예상과 다르면 `원본 결과`에서 입력 CSV 값을 확인합니다.

XAI 호출 결과에는 현재 토큰·재시도 계측값이 없으므로 공통 비교에서는 성공률과
처리 시간만 사용합니다. 값이 없는 항목은 `0`으로 채우지 않습니다.

`uploads/`는 Git 추적 대상이 아니므로 생성된 XLSX와 평가 결과 CSV는 커밋되지
않습니다. 보고서 생성 코드와 이 실행 문서만 형상 관리합니다.
