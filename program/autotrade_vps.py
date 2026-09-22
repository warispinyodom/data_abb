import asyncio
import os
from datetime import datetime, timedelta
from metaapi_cloud_sdk import MetaApi
import numpy as np
import pandas as pd

# ==========================================
# CONFIGURATION
# ==========================================
# นำ Token และ Account ID จากเว็บ MetaApi.cloud มาใส่ที่นี่
METAAPI_TOKEN = "ใส่_METAAPI_TOKEN_ที่นี่"
ACCOUNT_ID = "ใส่_ACCOUNT_ID_ที่นี่"

SYMBOL = "XAUUSDm"  # ชื่อ Symbol ในโบรกเกอร์ของคุณ
TIMEFRAME_ENTRY = "15m"  # Timeframe สำหรับหาจังหวะเข้า (M15)
TIMEFRAME_TREND = "1h"  # Timeframe เช็คเทรนด์ใหญ่ (H1)
RISK_PERCENT = 1.5  # ความเสี่ยงต่อไม้ (1.0% - 2.0%)
ADX_THRESHOLD = 25  # ค่าเกณฑ์ ADX ยืนยัน Trend
COOLDOWN_MINUTES = 15  # พักการเทรด 15 นาทีหากเพิ่งชน SL


# ==========================================
# INDICATOR CALCULATIONS
# ==========================================
async def fetch_data(connection, symbol, timeframe, count=100):
  try:
    candles = await connection.get_historical_candles(
        symbol, timeframe, limit=count
    )
    if not candles or len(candles) == 0:
      return None

    df = pd.DataFrame(candles)
    df['time'] = pd.to_datetime(df['time'])

    # EMA
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

    # ATR
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift(1)).abs()
    lc = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # ADX
    up = df['high'] - df['high'].shift(1)
    down = df['low'].shift(1) - df['low']
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    tr_smooth = tr.rolling(14).sum()
    plus_di = 100 * (pd.Series(plus_dm).rolling(14).sum() / (tr_smooth + 1e-9))
    minus_di = 100 * (
        pd.Series(minus_dm).rolling(14).sum() / (tr_smooth + 1e-9)
    )
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    df['adx'] = dx.rolling(14).mean()

    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs))

    return df
  except Exception:
    return None


# ==========================================
# AI SCORING & PROBABILITY ENGINE
# ==========================================
def ai_probability_analysis(df_entry, trend_h1):
  last = df_entry.iloc[-1]
  prev = df_entry.iloc[-2]

  score = 50.0  # Base Score

  if trend_h1 == 'BULLISH':
    if last['ema20'] > last['ema50']:
      score += 15
    if 50 < last['rsi'] < 70:
      score += 15
    if last['close'] > prev['high']:
      score += 10
  elif trend_h1 == 'BEARISH':
    if last['ema20'] < last['ema50']:
      score += 15
    if 30 < last['rsi'] < 50:
      score += 15
    if last['close'] < prev['low']:
      score += 10

  if last['adx'] > 30:
    score += 10

  probability = min(max(score, 0.0), 99.0)

  signal = 'NONE'
  if probability >= 65.0:
    signal = 'BUY' if trend_h1 == 'BULLISH' else 'SELL'

  return probability, signal, last['atr']


# ==========================================
# RISK MANAGEMENT & LOT SIZING
# ==========================================
def calculate_lot_size(balance, risk_percent, sl_distance):
  if sl_distance <= 0:
    return 0.01

  risk_amount = balance * (risk_percent / 100.0)
  # สำหรับ XAUUSD โดยประมาณ 1 Lot = $100 ต่อการแกว่ง 1 ดอลลาร์
  lot_size = risk_amount / (sl_distance * 100)

  lot_size = round(lot_size, 2)
  return max(0.01, min(10.0, lot_size))


# ==========================================
# COOLDOWN TRACKER
# ==========================================
async def check_sl_cooldown(connection, cooldown_minutes):
  try:
    now = datetime.now()
    from_time = now - timedelta(days=1)

    deals = await connection.get_deals_by_time_range(from_time, now)
    if not deals or 'deals' not in deals or len(deals['deals']) == 0:
      return False, 0

    sl_deals = [
        d for d in deals['deals'] if d.get('reason') == 'DEAL_REASON_SL'
    ]
    if not sl_deals:
      return False, 0

    last_sl_deal = max(sl_deals, key=lambda x: x['time'])
    last_sl_time = datetime.fromisoformat(
        last_sl_deal['time'].replace('Z', '+00:00')
    )
    time_diff = (
        datetime.now(last_sl_time.tzinfo) - last_sl_time
    ).total_seconds() / 60.0

    if time_diff < cooldown_minutes:
      return True, int(cooldown_minutes - time_diff)

    return False, 0
  except Exception:
    return False, 0


# ==========================================
# UI DASHBOARD
# ==========================================
def print_ui_dashboard(status_data):
  os.system('cls' if os.name == 'nt' else 'clear')
  print('===========================================================')
  print('          AI TRADING BOT (METAAPI CLOUD FOR LINUX CLI)     ')
  print('===========================================================')
  print(f" Timestamp    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  print(
      f" Account Bal  : ${status_data['balance']:,.2f} USD | Equity:"
      f" ${status_data['equity']:,.2f}"
  )
  print(f" Symbol       : {status_data['symbol']}")
  print('-----------------------------------------------------------')
  print(
      f" Cooldown SL  : {status_data['cooldown_status']} (Remaining:"
      f" {status_data['cooldown_min']} min)"
  )
  print(
      f" Trend H1     : {status_data['trend_h1']} (EMA20:"
      f" {status_data['ema20_h1']:.2f} | EMA50: {status_data['ema50_h1']:.2f})"
  )
  print(
      f" ADX Filter   : {status_data['adx_val']:.2f} ->"
      f" Status: {status_data['adx_status']}"
  )
  print('-----------------------------------------------------------')
  print(
      f" AI Probability: {status_data['ai_prob']:.1f}% | Signal:"
      f" {status_data['ai_signal']}"
  )
  print(
      f" Target Price  : Entry ~ {status_data['entry_price']} | SL:"
      f" {status_data['sl']} | TP: {status_data['tp']}"
  )
  print(
      f" Calculated Lot: {status_data['lot_size']} Lots (Risk"
      f" {RISK_PERCENT}%)"
  )
  print('-----------------------------------------------------------')
  print(f" Active Orders : {status_data['active_positions']}")
  print(f" Action Status : {status_data['current_action']}")
  print('===========================================================')


# ==========================================
# MAIN ASYNC LOOP (10-SECOND CYCLE)
# ==========================================
async def main():
  api = MetaApi(METAAPI_TOKEN)
  account = await api.metatrader_account_api.get_account(ACCOUNT_ID)

  print('[1/2] Connecting to MetaApi Cloud Server...')
  await account.wait_connected()

  connection = account.get_rpc_connection()
  await connection.connect()
  await connection.wait_synchronized()
  print('[2/2] Connected Successfully! Starting Trading Loop...\n')

  while True:
    try:
      action_msg = 'Waiting for condition match...'

      # 1. ดึงข้อมูลพอร์ตและราคา Real-time
      acc_info = await connection.get_account_information()
      price_info = await connection.get_symbol_price(SYMBOL)

      balance = acc_info['balance']
      equity = acc_info['equity']
      ask = price_info['ask']
      bid = price_info['bid']

      # 2. เช็ค Cooldown SL
      in_cooldown, cooldown_rem = await check_sl_cooldown(
          connection, COOLDOWN_MINUTES
      )

      # 3. ดึง Candlesticks
      df_h1 = await fetch_data(connection, SYMBOL, TIMEFRAME_TREND)
      df_entry = await fetch_data(connection, SYMBOL, TIMEFRAME_ENTRY)

      if df_h1 is None or df_entry is None:
        await asyncio.sleep(10)
        continue

      # 4. เช็คเทรนด์ H1
      last_h1 = df_h1.iloc[-1]
      trend_h1 = (
          'BULLISH' if last_h1['ema20'] > last_h1['ema50'] else 'BEARISH'
      )

      # 5. เช็ค ADX Filter
      adx_val = df_entry.iloc[-1]['adx']
      adx_passed = adx_val >= ADX_THRESHOLD
      adx_status = 'TRENDING (PASS)' if adx_passed else 'SIDEWAY (SKIP)'

      # 6. AI Probability Analysis
      prob, signal, atr = ai_probability_analysis(df_entry, trend_h1)

      # คำนวณ SL / TP (RR ~ 1:2)
      current_price = ask if trend_h1 == 'BULLISH' else bid
      sl_distance = atr * 1.5
      tp_distance = atr * 3.0

      if trend_h1 == 'BULLISH':
        sl_price = round(current_price - sl_distance, 2)
        tp_price = round(current_price + tp_distance, 2)
      else:
        sl_price = round(current_price + sl_distance, 2)
        tp_price = round(current_price - tp_distance, 2)

      calculated_lot = calculate_lot_size(balance, RISK_PERCENT, sl_distance)

      # เช็คจำนวน Position ที่เปิดอยู่
      positions = await connection.get_positions()
      active_positions = [p for p in positions if p['symbol'] == SYMBOL]
      num_positions = len(active_positions)

      # Execution Logic
      if num_positions > 0:
        action_msg = 'Holding open position. Skip new order.'
      elif in_cooldown:
        action_msg = f'In Cooldown state ({cooldown_rem} mins remaining).'
      elif not adx_passed:
        action_msg = f'Market is Sideway (ADX {adx_val:.1f} < 25).'
      elif signal != 'NONE':
        # ส่งออเดอร์ผ่าน MetaApi
        if signal == 'BUY':
          res = await connection.create_market_buy_order(
              symbol=SYMBOL,
              volume=calculated_lot,
              stop_loss=sl_price,
              take_profit=tp_price,
          )
        else:
          res = await connection.create_market_sell_order(
              symbol=SYMBOL,
              volume=calculated_lot,
              stop_loss=sl_price,
              take_profit=tp_price,
          )

        action_msg = (
            f"SUCCESS: Opened {signal} Order (ID: {res.get('orderId', '')})"
        )

      # อัปเดต UI Dashboard
      dashboard_data = {
          'balance': balance,
          'equity': equity,
          'symbol': SYMBOL,
          'cooldown_status': 'ACTIVE' if in_cooldown else 'NORMAL',
          'cooldown_min': cooldown_rem,
          'trend_h1': trend_h1,
          'ema20_h1': last_h1['ema20'],
          'ema50_h1': last_h1['ema50'],
          'adx_val': adx_val,
          'adx_status': adx_status,
          'ai_prob': prob,
          'ai_signal': signal,
          'entry_price': current_price,
          'sl': sl_price,
          'tp': tp_price,
          'lot_size': calculated_lot,
          'active_positions': num_positions,
          'current_action': action_msg,
      }

      print_ui_dashboard(dashboard_data)

    except Exception as e:
      print(f'Error in loop: {e}')

    # วนรอบทุก 10 วินาที
    await asyncio.sleep(10)


if __name__ == '__main__':
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    print('\n===========================================================')
    print(' [!] ผู้ใช้สั่งหยุดการทำงานของโปรแกรมเรียบร้อยแล้ว')
    print('===========================================================')