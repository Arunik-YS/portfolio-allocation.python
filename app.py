import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
from scipy.optimize import minimize

# 1. 페이지 설정
st.set_page_config(page_title="주식 최적 배분 계산기", layout="centered")

# 모바일 UI 최적화를 위한 CSS (입력창 하단 여백 조정)
st.markdown("""
    <style>
    .stNumberInput, .stTextInput { margin-bottom: -15px; }
    </style>
    """, unsafe_allow_html=True)

# 2. 실시간 가격 가져오기 (Streamlit Cloud IP 차단 우회 적용)
@st.cache_data(show_spinner=False)
def get_stock_info(ticker):
    try:
        # yf.Ticker 대신 yf.download를 사용해 IP 차단 확률을 대폭 낮춥니다.
        # period="5d"를 주어 주말/휴장일이 끼어있어도 안정적으로 데이터를 가져옵니다.
        df = yf.download(ticker, period="5d", progress=False)
        if df.empty:
            return None, None
        
        # yfinance 버전이나 단일/다중 티커 조회에 따라 컬럼 구조(MultiIndex)가 다를 수 있어 이를 분기 처리합니다.
        if isinstance(df.columns, pd.MultiIndex):
            price = float(df['Close'][ticker].iloc[-1])
        else:
            price = float(df['Close'].iloc[-1])
            
        # 종목명은 입력한 티커를 그대로 사용합니다 (종목명 조회를 위한 추가 API 호출 방지)
        return ticker, price
    except Exception as e:
        return None, None
        
        price = float(hist['Close'].iloc[-1])
        # info에서 이름을 가져오되, 실패하면 입력한 티커를 그대로 사용
        name = stock.info.get('shortName', stock.info.get('longName', ticker))
        return name, price
    except Exception as e:
        return None, None

# 3. 과거 3개월 데이터 가져오기
@st.cache_data(show_spinner=False)
def fetch_history(tickers):
    data = yf.download(tickers, period="3mo")['Adj Close']
    return data

# 4. 포트폴리오 연산 로직
def portfolio_performance(weights, mean_returns, cov_matrix, risk_free_rate):
    returns = np.sum(mean_returns * weights) * 252
    std_dev = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(252)
    sharpe_ratio = (returns - risk_free_rate) / std_dev
    return returns, std_dev, sharpe_ratio

def negative_sharpe(weights, mean_returns, cov_matrix, risk_free_rate):
    return -portfolio_performance(weights, mean_returns, cov_matrix, risk_free_rate)[2]

# ==========================================
# UI 렌더링 시작
# ==========================================
st.title("⚖️ 포트폴리오 리밸런싱")

st.subheader("🔍 보유 종목 입력")
tickers_input = []
shares_input = []
current_values = []
current_prices = []

# 5. 티커와 주수 묶음 처리 (가시성 향상)
for i in range(5):
    # container(border=True)를 사용하여 입력칸들을 카드 형태로 박스 처리합니다.
    with st.container(border=True):
        col1, col2 = st.columns([1, 1])
        with col1:
            t = st.text_input(f"종목 {i+1} 티커", key=f"t{i}", placeholder="예: TQQQ").upper().strip()
        with col2:
            s = st.number_input(f"보유 주수 (주)", key=f"s{i}", min_value=0, step=1)
        
        if t:
            name, price = get_stock_info(t)
            if price:
                eval_amount = price * s
                # 정보 텍스트를 카드 하단에 깔끔하게 표시
                st.info(f"📍 **{name}** | 현재가: ${price:.2f} | 평가금: **${eval_amount:,.2f}**")
                
                tickers_input.append(t)
                shares_input.append(s)
                current_prices.append(price)
                current_values.append(eval_amount)
            else:
                st.error("⚠️ 데이터를 불러올 수 없는 티커입니다.")

st.divider()

# 6. 투자금액 설정 섹션
st.subheader("💰 자금 설정")
total_eval = sum(current_values)

colA, colB = st.columns(2)
with colA:
    st.metric("현재 총 평가금액", f"${total_eval:,.2f}")
with colB:
    add_cash = st.number_input("추가 투자 금액 ($)", min_value=0.0, value=0.0, step=100.0)

total_budget = total_eval + add_cash
st.success(f"총 가용 자산 (평가금 + 추가금): **${total_budget:,.2f}**")

# 7. 분석 실행
risk_free_rate = 0.03 # 무위험수익률 3% 가정

if st.button("🚀 최적 배분 시뮬레이션 실행", use_container_width=True, type="primary"):
    if len(tickers_input) < 2:
        st.warning("분석을 위해 최소 2개 이상의 유효한 티커를 입력해주세요.")
    else:
        with st.spinner("과거 데이터를 분석하고 최적 비중을 계산 중입니다..."):
            history = fetch_history(tickers_input)
            log_returns = np.log(history / history.shift(1)).dropna()
            mean_returns = log_returns.mean()
            cov_matrix = log_returns.cov()
            
            num_assets = len(tickers_input)
            constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
            
            # 수정: 모든 종목 최소 15%(0.15) ~ 최대 100%(1.0) 제한
            min_weight = 0.15 
            bounds = tuple((min_weight, 1.0) for _ in range(num_assets)) 
            
            init_guess = num_assets * [1. / num_assets,]
            
            opt_result = minimize(negative_sharpe, init_guess, 
                                  args=(mean_returns, cov_matrix, risk_free_rate),
                                  method='SLSQP', bounds=bounds, constraints=constraints)
            
            weights = opt_result.x
            
            # 결과 출력
            st.subheader("📊 종목별 매수 가이드")
            
            results_data = []
            for i in range(len(tickers_input)):
                target_amount = total_budget * weights[i]
                target_shares = target_amount / current_prices[i]
                diff_shares = target_shares - shares_input[i]
                
                results_data.append({
                    "티커": tickers_input[i],
                    "최적 비중": f"{weights[i]*100:.1f}%",
                    "목표 주수": f"{target_shares:.2f}주",
                    "매수 필요": f"{max(0, diff_shares):.2f}주"
                })
            
            # 테이블 가시성을 위해 Dataframe 활용
            st.dataframe(pd.DataFrame(results_data), use_container_width=True, hide_index=True)
            
            st.subheader("📈 포트폴리오 예상 성과")
            ret, std, sharpe = portfolio_performance(weights, mean_returns, cov_matrix, risk_free_rate)
            
            pc1, pc2, pc3 = st.columns(3)
            pc1.metric("연환산 수익률", f"{ret*100:.2f}%")
            pc2.metric("연환산 변동성", f"{std*100:.2f}%")
            pc3.metric("샤프 지수", f"{sharpe:.2f}")
