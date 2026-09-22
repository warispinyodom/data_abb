import os
import time
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import numpy as np
import pandas as pd

# ==========================================
# CONFIGURATION
# ==========================================
SYMBOL = "XAUUSDm"  # ชื่อ Symbol ใน MT5
TIMEFRAME_ENTRY = mt5.TIMEFRAME_M15  # Timeframe สำหรับหาจังหวะเข้า
TIMEFRAME_TREND = mt5.TIMEFRAME_H1  # Timeframe เช็คเทรนด์ใหญ่
RISK_PERCENT = 1.5  # ความเสี่ยงต่อไม้ (1.0% - 2.0%)
ADX_THRESHOLD = 25  # ค่าเกณฑ์ ADX ยืนยัน Trend
COOLDOWN_MINUTES = 15  # พักการเทรด 15 นาทีหากเพิ่งชน SL
MAGIC_NUMBER = 998877  # ID ออเดอร์ของบอท


# ==========================================
# INDICATOR CALCULATIONS
# ==========================================
def fetch_data(symbol, timeframe, count=100):
  rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
  if rates is None or len(rates) == 0:
    return None
  df = pd.DataFrame(rates)
  df['time'] = pd.to_datetime(df['time'], unit='s')

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
  plus_di = 100 * (pd.Series(plus_dm).rolling(14).sum() / tr_smooth)
  minus_di = 100 * (pd.Series(minus_dm).rolling(14).sum() / tr_smooth)
  dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
  df['adx'] = dx.rolling(14).mean()

  # RSI
  delta = df['close'].diff()
  gain = (delta.where(delta > 0, 0)).rolling(14).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
  rs = gain / (loss + 1e-9)
  df['rsi'] = 100 - (100 / (1 + rs))

  return df


# ==========================================
# AI SCORING & PROBABILITY ENGINE
# ==========================================
def ai_probability_analysis(df_entry, trend_h1):
  """คำนวณคะแนนความน่าจะเป็น (0 - 100%) ในการเข้าเทรด"""
  last = df_entry.iloc[-1]
  prev = df_entry.iloc[-2]

  score = 50.0  # Base Score

  # 1. Indicator Momentum alignment (+15%)
  if trend_h1 == 'BULLISH':
    if last['ema20'] > last['ema50']:
      score += 15
    if last['rsi'] > 50 and last['rsi'] < 70:
      score += 15
    if last['close'] > prev['high']:
      score += 10
  elif trend_h1 == 'BEARISH':
    if last['ema20'] < last['ema50']:
      score += 15
    if last['rsi'] < 50 and last['rsi'] > 30:
      score += 15
    if last['close'] < prev['low']:
      score += 10

  # 2. ADX Strength Bonus (+10%)
  if last['adx'] > 30:
    score += 10

  probability = min(max(score, 0.0), 99.0)

  # ตัดสินใจสัญญาณเข้าเทรดถ้าความน่าจะเป็น >= 65%
  signal = 'NONE'
  if probability >= 65.0:
    signal = 'BUY' if trend_h1 == 'BULLISH' else 'SELL'

  return probability, signal, last['atr']


# ==========================================
# RISK MANAGEMENT & LOT SIZING
# ==========================================
def calculate_lot_size(symbol, risk_percent, sl_pips):
  account_info = mt5.account_info()
  symbol_info = mt5.symbol_info(symbol)
  if account_info is None or symbol_info is None:
    return 0.01

  balance = account_info.balance
  risk_amount = balance * (risk_percent / 100.0)

  # คำนวณมูลค่าจุดของทองคำ (XAUUSD)
  point_value = symbol_info.trade_tick_value / symbol_info.trade_tick_size
  sl_distance = sl_pips * symbol_info.point

  if sl_distance == 0:
    return symbol_info.volume_min

  lot_size = risk_amount / (sl_distance * point_value)

  # ปรับขนาด Lot ให้ตรงตามเงื่อนไขของโบรกเกอร์
  step = symbol_info.volume_step
  lot_size = round(lot_size / step) * step
  lot_size = max(
      symbol_info.volume_min, min(symbol_info.volume_max, lot_size)
  )

  return round(lot_size, 2)


# ==========================================
# COOLDOWN TRACKER
# ==========================================
def check_sl_cooldown(symbol, cooldown_minutes):
  now = datetime.now()
  from_time = now - timedelta(days=1)

  history_deals = mt5.history_deals_get(from_time, now, group=f'*{symbol}*')
  if history_deals is None or len(history_deals) == 0:
    return False, 0

  # ค้นหา Deal ล่าสุดที่ถูกปิดด้วย Stop Loss
  sl_deals = [
      d
      for d in history_deals
      if d.entry == mt5.DEAL_ENTRY_OUT and d.reason == mt5.DEAL_REASON_SL
  ]
  if not sl_deals:
    return False, 0

  last_sl_time = datetime.fromtimestamp(sl_deals[-1].time)
  time_diff = (now - last_sl_time).total_seconds() / 60.0

  if time_diff < cooldown_minutes:
    remaining_cooldown = int(cooldown_minutes - time_diff)
    return True, remaining_cooldown

  return False, 0


# ==========================================
# EXECUTION ENGINE
# ==========================================
def execute_trade(symbol, order_type, lot, sl_price, tp_price):
  price = (
      mt5.symbol_info_tick(symbol).ask
      if order_type == 'BUY'
      else mt5.symbol_info_tick(symbol).bid
  )
  cmd = mt5.ORDER_TYPE_BUY if order_type == 'BUY' else mt5.ORDER_TYPE_SELL

  request = {
      'action': mt5.TRADE_ACTION_DEAL,
      'symbol': symbol,
      'volume': lot,
      'type': cmd,
      'price': price,
      'sl': sl_price,
      'tp': tp_price,
      'deviation': 20,
      'magic': MAGIC_NUMBER,
      'comment': 'AI Trade Entry',
      'type_time': mt5.ORDER_TIME_GTC,
      'type_filling': mt5.ORDER_FILLING_IOC,
  }

  res = mt5.order_send(request)
  return res.retcode == mt5.TRADE_RETCODE_DONE


# ==========================================
# UI DASHBOARD
# ==========================================
def print_ui_dashboard(status_data):
  os.system('cls' if os.name == 'nt' else 'clear')
  print('===========================================================')
  print('               AI TRADING BOT SYSTEM (MT5)                ')
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
  print(f" Calculated Lot: {status_data['lot_size']} Lots (Risk 1.5%)")
  print('-----------------------------------------------------------')
  print(f" Active Orders : {status_data['active_positions']}")
  print(f" Action Status : {status_data['current_action']}")
  print('===========================================================')


# ==========================================
# MAIN LOOP (10-SECOND CYCLE)
# ==========================================
def main():
  if not mt5.initialize():
    print('Failed to connect MetaTrader 5')
    return

  print(f'MT5 Connected Successfully. Monitoring {SYMBOL}...')

  while True:
    action_msg = 'Waiting for condition match...'
    acc = mt5.account_info()
    tick = mt5.symbol_info_tick(SYMBOL)

    if acc is None or tick is None:
      time.sleep(10)
      continue

    # 1. เช็ค Cooldown
    in_cooldown, cooldown_rem = check_sl_cooldown(SYMBOL, COOLDOWN_MINUTES)

    # 2. เช็ค Data & Indicators
    df_h1 = fetch_data(SYMBOL, TIMEFRAME_TREND)
    df_entry = fetch_data(SYMBOL, TIMEFRAME_ENTRY)

    if df_h1 is None or df_entry is None:
      time.sleep(10)
      continue

    # 3. เช็คเทรนด์ใหญ่ H1
    last_h1 = df_h1.iloc[-1]
    trend_h1 = (
        'BULLISH' if last_h1['ema20'] > last_h1['ema50'] else 'BEARISH'
    )

    # 4. เช็ค ADX
    adx_val = df_entry.iloc[-1]['adx']
    adx_passed = adx_val >= ADX_THRESHOLD
    adx_status = 'TRENDING (PASS)' if adx_passed else 'SIDEWAY (SKIP)'

    # 5. AI Probability Analysis
    prob, signal, atr = ai_probability_analysis(df_entry, trend_h1)

    # คำนวณ SL / TP โดย AI ใช้ค่า ATR (RR ~ 1:2)
    current_price = tick.ask if trend_h1 == 'BULLISH' else tick.bid
    sl_distance = atr * 1.5
    tp_distance = atr * 3.0

    if trend_h1 == 'BULLISH':
      sl_price = round(current_price - sl_distance, 2)
      tp_price = round(current_price + tp_distance, 2)
    else:
      sl_price = round(current_price + sl_distance, 2)
      tp_price = round(current_price - tp_distance, 2)

    sl_pips = abs(current_price - sl_price) / mt5.symbol_info(SYMBOL).point
    calculated_lot = calculate_lot_size(SYMBOL, RISK_PERCENT, sl_pips)

    # เช็คจำนวนการเปิด Position ล่าสุด
    open_positions = mt5.positions_get(symbol=SYMBOL)
    num_positions = len(open_positions) if open_positions else 0

    # Execute Logic ตามลำดับเงื่อนไข
    if num_positions > 0:
      action_msg = 'Holding open position. Skip new order.'
    elif in_cooldown:
      action_msg = f'In Cooldown state ({cooldown_rem} mins remaining).'
    elif not adx_passed:
      action_msg = f'Market is Sideway (ADX {adx_val:.1f} < 25).'
    elif signal != 'NONE':
      # สั่งซื้อขายเมื่อผ่านทุกเงื่อนไข
      success = execute_trade(SYMBOL, signal, calculated_lot, sl_price, tp_price)
      if success:
        action_msg = f'SUCCESS: Opened {signal} order at {current_price}'
      else:
        action_msg = f'FAILED: Error executing {signal} order'

    # อัปเดต UI Dashboard
    dashboard_data = {
        'balance': acc.balance,
        'equity': acc.equity,
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

    # ทำงานวนรอบทุกๆ 10 วินาที
    time.sleep(10)


if __name__ == '__main__':
  try:
    main()
  except KeyboardInterrupt:
    print('\n' + '=' * 59)
    print(' [!] ผู้ใช้สั่งหยุดการทำงานของโปรแกรม (KeyboardInterrupt)')
    print('=' * 59)
  finally:
    # ปิดการเชื่อมต่อ MT5 อย่างปลอดภัยเมื่อปิดโปรแกรม
    mt5.shutdown()
    print(' [!] ปิดการเชื่อมต่อ MetaTrader 5 เรียบร้อยแล้ว')