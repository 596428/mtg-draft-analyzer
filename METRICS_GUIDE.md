# MTG Draft Guide - Metrics Explanation

**Site**: https://mtg-ecl-draft-guide.netlify.app

---

## 📊 Format Overview

### Format Speed
**계산식**: `tempo_ratio = avg(OH WR) / avg(GD WR)`

- **OH WR** (Opening Hand Win Rate): 오프닝 핸드에 있을 때 승률
- **GD WR** (Games Drawn Win Rate): 게임 중 드로우했을 때 승률

| Tempo Ratio | 속도 | 의미 |
|-------------|------|------|
| ≥ 1.03 | 빠름 | 초반 카드가 강함 → 어그로 유리 |
| 0.99~1.03 | 보통 | 균형 잡힌 포맷 |
| 0.96~0.99 | 약간 느림 | 후반 카드가 약간 강함 |
| < 0.96 | 느림 | 드로우 카드가 강함 → 컨트롤 유리 |

---

### Splash Viability & Dual Land ALSA
**Dual Land ALSA**: 듀얼랜드가 평균 몇 번째 픽에 남아있는지

| ALSA | 스플래시 난이도 |
|------|----------------|
| < 5.5 | 경쟁 치열 → 조기 픽 필요 |
| 5.5~7.5 | 보통 |
| > 8.0 | 늦게 돌아옴 → 스플래시 용이 |

듀얼랜드 개수와 ALSA를 종합하여 스플래시 난이도를 판단합니다.

---

## ⭐ Card Ratings

### Score (종합 점수)
**계산 방식**: 각 지표의 Z-Score를 가중 합산 후 0-100 스케일로 변환

| 지표 | 가중치 | 설명 |
|------|--------|------|
| GIH WR | 45% | 핸드에 들어왔을 때 승률 (Bayesian 보정) |
| IWD | 20% | GIH WR - GNS WR (드로우 시 승률 향상) |
| ALSA | 15% | 픽 순위 (낮을수록 좋음) |
| OH WR | 10% | 오프닝 핸드 승률 |
| GD WR | 10% | 드로우 승률 |

**Z-Score 변환**: `Score = 50 + (가중합 Z-Score × 15)`
- Z=0 (평균) → 50점
- Z=+2 (상위 2.5%) → 80점
- Z=-2 (하위 2.5%) → 20점

---

### GIH Win Rate
**데이터 출처**: 17lands API의 `ever_drawn_win_rate`

핸드에 해당 카드가 들어왔을 때의 실제 승률입니다.
Wilson Score Lower Bound를 적용하여 샘플 수가 적은 카드는 50%로 회귀합니다.

---

### Stability (안정성)
**계산식**: `Stability = 100 - (아키타입별 승률 분산 × 보정계수)`

| Stability | 의미 |
|-----------|------|
| 80~100 | 어느 덱에서나 안정적으로 활약 |
| 50~80 | 덱에 따라 성능 차이 있음 |
| < 50 | 특정 아키타입에서만 강함 (시너지 의존) |

10개 2색 조합에서의 승률 편차가 클수록 Stability가 낮아집니다.

---

## 💎 Sleepers & Traps

### 판별 로직
**1단계 - 기대 승률 계산**:
```
Expected WR = 50% + (Pick Rate × 12%) + ((7 - ALSA) × 1.5%)
```
- 픽률이 높고 일찍 픽되는 카드 → 높은 기대 승률

**2단계 - 편차 계산**:
```
Deviation = Actual WR (Bayesian) - Expected WR
```

**3단계 - Z-Score 분류**:
- **Sleeper**: Deviation Z-Score ≥ 0.75 (기대보다 훨씬 좋음)
- **Trap**: Deviation Z-Score ≤ -0.63 (기대보다 훨씬 나쁨)
- **Normal**: 그 외

---

### Sleeper 카드
- 늦게 픽되거나 픽률이 낮지만 실제 승률은 높은 카드
- 저평가되어 있으므로 늦게 획득 가능
- 예: 지루해 보이지만 실전에서 강한 유틸리티 카드

### Trap 카드
- 일찍 픽되거나 픽률이 높지만 실제 승률은 낮은 카드
- 고평가되어 있으므로 픽 우선순위를 낮춰야 함
- 예: 화려해 보이지만 실전에서 약한 카드

---

### GIH Win Rate 0% 표시 이유

특정 카드가 **GIH WR: 0%**, **Score: 0점**으로 표시되는 이유:

1. **해당 세트에 없는 카드**
   - 17lands 데이터에는 있지만 Scryfall에서 해당 세트로 검색되지 않음
   - 예: Bitterblossom, Door of Destinies (ECL 세트에 없음)
   - 이미지도 로드되지 않아 UI에서 필터링됨

2. **데이터 품질 이슈**
   - 17lands API에서 `ever_drawn_win_rate` 값이 null/0으로 반환
   - 게임 수가 너무 적어 승률 계산이 불가능한 경우

3. **전처리 필터링**
   - `gih_games < 200` (최소 게임 수 미달)인 카드는 분석에서 제외
   - 제외된 카드는 기본값 0으로 처리됨

**참고**: Sleepers & Traps 섹션에서는 이미지가 있는 카드만 표시되므로, 0% 카드는 자동으로 필터링됩니다.

---

*Data Source: 17lands.com (Premier Draft)*
