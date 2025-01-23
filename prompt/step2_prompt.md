다음 단계로 분석하세요.  
1. **차별성 검증**:  
   - 본문에 1차 판단에서 발견된 키워드 외 **새로운 고유 정보** (통계, 전문가 발언)가 있는지 확인.  
   - 예시: "소상공인 매출 30% 증가 예상" → 데이터 기반 차별성.  
2. **파급력 심화 평가**:  
   - 본문에서 영향력 있는 기관/정책 언급 횟수 (ex: "정부", "전문가", "법안").  
   - 장기적 효과 예측 (경제, 사회 분야).  
3. **긴급성 재확인**:  
   - 구체적인 시간/조건 (ex: "11월 1일 0시부터", "변이 바이러스 유입 시 재검토") 포함 여부.  
4. **신뢰도 추가**:  
   - 출처 명시된 데이터/전문가 인용 횟수.  

**출력 형식**:  
{
  "final_unique": 0~10,  
  "final_impact": 0~10,  
  "final_urgency": 0~10,  
  "credibility_score": 0~5 (출처/데이터 기반),  
  "recommendation": "high/mid/low" (총점 ≥ 25점 → high)  
}