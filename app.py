import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
from scipy.optimize import minimize

# 페이지 설정
st.set_page_config(page_title="주식 최적 배분 계산기", layout="centered")

# CSS를 활용해 모바일에서 입력 칸 간격 조정
st.markdown("""
    <style>
    .stNumberInput, .stTextInput { margin-bottom: -15px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def get_stock_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        # 실시간 가격 및 종목명 가져오기
        fast_info = stock.fast_info
        price = fast_info['last_price']
        name = stock.info.get('longName', ticker)
        return name, price
    except:
        return None, None

@st.cache_data(show_spinner=False)
def fetch_history(tickers):
    data = yf.download(tickers, period="3mo")['Adj Close']
    return data

# 포트폴리오 연산 로직 (이전과 동일)
def portfolio_performance(weights, mean_returns, cov_matrix, risk_free_rate):
    returns = np.sum(mean_returns * weights) * 252
    std_dev = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(252)
    sharpe_ratio = (returns - risk_free_rate) / std_dev
    return returns, std_dev, sharpe_ratio

def negative_sharpe(weights, mean_returns, cov_matrix, risk_free_rate):
    return -portfolio_performance(weights, mean_returns, cov_matrix, risk_free_rate)[2]

# --- UI 시작 ---
st.title("⚖️ 포트폴리오 리밸런싱")

# 1. 티커 및 보유 주수 입력 섹션
st.subheader("🔍 보유 종목 입력")
tickers_input = []
shares_input = []
current_values = []
current_prices = []

# 5개의 입력 칸 생성
for i in range(5):
    col1, col2 = st.columns([1, 1])
    with col1:
        t = st.text_input(f"티커 {i+1}", key=f"t{i}", placeholder="예: TQQQ").upper().strip()
    with col2:
        s = st.number_input(f"현재 주수", key=f"s{i}", min_value=0, step=1)
    
    if t:
        name, price = get_stock_info(t)
        if price:
            eval_amount = price * s
            st.caption(f"📍 {name} | 현재가: ${price:.2f} | 평가금: ${eval_amount:,.2f}")
            tickers_input.append(t)
            shares_input.append(s)
            current_prices.append(price)
            current_values.append(eval_amount)
        else:
            st.caption("⚠️ 유효하지 않은 티커입니다.")

st.divider()

# 2. 투자금액 설정 섹션
st.subheader("💰 자금 설정")
total_eval = sum(current_values)
st.metric("현재 총 평가금액", f"${total_eval:,.2f}")

add_cash = st.number_input("추가 투자 금액 ($)", min_value=0, value=0, step=100)
total_budget = total_eval + add_cash
st.info(f"계산 기준 총 금액 (평가금 + 추가금): **${total_budget:,.2f}**")

# 3. 분석 실행
risk_free_rate = 0.03 # 국고채 3년물 가정 (3%)

if st.button("🚀 최적 배분 시뮬레이션 실행", use_container_width=True):
    if len(tickers_input) < 2:
        st.error("분석을 위해 최소 2개 이상의 유효한 티커가 필요합니다.")
    else:
        with st.spinner("과거 데이터를 분석하고 최적 비중을 계산 중입니다..."):
            # 데이터 수집 및 연산
            history = fetch_history(tickers_input)
            log_returns = np.log(history / history.shift(1)).dropna()
            mean_returns = log_returns.mean()
            cov_matrix = log_returns.cov()
            
            # 최적화 (Sharpe 최대화)
            num_assets = len(tickers_input)
            constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
            bounds = tuple((0, 1) for _ in range(num_assets))
            init_guess = num_assets * [1. / num_assets,]
            
            opt_result = minimize(negative_sharpe, init_guess, 
                                  args=(mean_returns, cov_matrix, risk_free_rate),
                                  method='SLSQP', bounds=bounds, constraints=constraints)
            
            weights = opt_result.x
            
            # 4. 결과 출력
            st.success("분석 완료!")
            
            # 종목별 결과 리스트
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
            
            st.subheader("📊 종목별 매수 가이드")
            st.table(pd.DataFrame(results_data))
            
            # 포트폴리오 성과 수치
            ret, std, sharpe = portfolio_performance(weights, mean_returns, cov_matrix, risk_free_rate)
            cols = st.columns(2)
            cols[0].metric("예상 수익률", f"{ret*100:.2f}%")
            cols[1].metric("샤프 지수", f"{sharpe:.2f}")
