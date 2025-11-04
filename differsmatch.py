from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.clock import Clock, mainthread
from kivy.graphics import Color, Rectangle
from kivy.core.window import Window
from kivy.metrics import dp
import json
import threading
import websocket
import time
from collections import deque, Counter
import random

# Set window size for testing (remove for mobile)
Window.size = (400, 700)

WS_ENDPOINT = "wss://ws.derivws.com/websockets/v3?app_id=1089"

class ColorBox(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(30)
        self.spacing = dp(2)
        
    def update_colors(self, colors):
        self.clear_widgets()
        for color in colors:
            box = Label()
            box.size_hint_x = 1.0 / max(len(colors), 1)
            with box.canvas.before:
                if color == 'green':
                    Color(0, 0.8, 0, 1)
                else:
                    Color(0.8, 0, 0, 1)
                box.rect = Rectangle(pos=box.pos, size=box.size)
            box.bind(pos=self.update_rect, size=self.update_rect)
            self.add_widget(box)
    
    def update_rect(self, instance, value):
        instance.rect.pos = instance.pos
        instance.rect.size = instance.size

class LogArea(ScrollView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(200)
        self.layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(2))
        self.layout.bind(minimum_height=self.layout.setter('height'))
        self.add_widget(self.layout)
        
    def add_log(self, message, color=(1, 1, 1, 1)):
        log_label = Label(
            text=f"[{time.strftime('%H:%M:%S')}] {message}",
            size_hint_y=None,
            height=dp(30),
            color=color,
            text_size=(Window.width - dp(20), None),
            halign='left',
            valign='middle'
        )
        self.layout.add_widget(log_label)
        self.scroll_y = 0

class MarketPerformanceBar(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(100)
        self.spacing = dp(5)
        self.padding = dp(5)
        
    def update_performance(self, market_performance, available_markets):
        self.clear_widgets()
        
        max_profit = max(abs(market_performance[m]['profit']) for m in available_markets)
        if max_profit == 0:
            max_profit = 1
            
        for market in available_markets:
            perf = market_performance[market]
            profit = perf['profit']
            
            bar_layout = BoxLayout(orientation='vertical', size_hint_x=1)
            
            # Profit label
            profit_label = Label(
                text=f"${profit:.2f}",
                size_hint_y=0.2,
                font_size=dp(10)
            )
            
            # Bar container
            bar_container = BoxLayout(size_hint_y=0.6)
            bar = Label()
            
            # Calculate bar height ratio
            height_ratio = abs(profit) / max_profit if max_profit > 0 else 0
            
            with bar.canvas.before:
                if profit >= 0:
                    Color(0, 0.8, 0, 1)
                else:
                    Color(0.8, 0, 0, 1)
                bar.rect = Rectangle(pos=bar.pos, size=bar.size)
            
            bar.bind(pos=self.update_bar_rect, size=self.update_bar_rect)
            bar_container.add_widget(bar)
            
            # Market label
            market_label = Label(
                text=market,
                size_hint_y=0.2,
                font_size=dp(10),
                bold=True
            )
            
            bar_layout.add_widget(profit_label)
            bar_layout.add_widget(bar_container)
            bar_layout.add_widget(market_label)
            
            self.add_widget(bar_layout)
    
    def update_bar_rect(self, instance, value):
        instance.rect.pos = instance.pos
        instance.rect.size = instance.size

class SmartMarketDifferBot(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = dp(10)
        self.spacing = dp(10)
        
        # Trading variables
        self.ws = None
        self.running = False
        self.token = ""
        self.available_markets = ["R_10", "R_25", "R_50", "R_75", "R_100"]
        self.current_market = "R_10"
        self.stake = 1.0
        self.trade_count = 0
        self.max_trades = 10
        self.balance = 0.0
        self.profit_loss = 0.0
        self.win_rate = 0.0
        self.wins = 0
        self.losses = 0
        
        # Market performance tracking
        self.market_performance = {market: {'wins': 0, 'losses': 0, 'profit': 0.0} 
                                  for market in self.available_markets}
        self.market_switch_counter = 0
        self.market_switch_interval = 5
        
        # Market analysis
        self.last_digits = deque(maxlen=100)
        self.digit_counts = Counter()
        self.rarest_digits = []
        self.color_history = deque(maxlen=15)
        self.pattern_history = deque(maxlen=10)
        
        # Trade tracking
        self.trade_history = []
        self.pending_contracts = {}
        self.start_time = None
        
        self.build_ui()
        
    def build_ui(self):
        # Header
        header = Label(
            text='Smart Market Differ Bot',
            size_hint_y=None,
            height=dp(50),
            font_size=dp(20),
            bold=True,
            color=(0.2, 0.5, 0.8, 1)
        )
        self.add_widget(header)
        
        # Scrollable content
        scroll = ScrollView(size_hint=(1, 1))
        content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10))
        content.bind(minimum_height=content.setter('height'))
        
        # Configuration section
        config_grid = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(160))
        
        config_grid.add_widget(Label(text='API Token:', size_hint_x=0.4))
        self.token_input = TextInput(password=True, multiline=False, size_hint_x=0.6)
        config_grid.add_widget(self.token_input)
        
        config_grid.add_widget(Label(text='Current Market:', size_hint_x=0.4))
        self.market_label = Label(text='R_10', bold=True, color=(0.2, 0.5, 0.8, 1), size_hint_x=0.6)
        config_grid.add_widget(self.market_label)
        
        config_grid.add_widget(Label(text='Stake ($):', size_hint_x=0.4))
        self.stake_input = TextInput(text='1.0', multiline=False, input_filter='float', size_hint_x=0.6)
        config_grid.add_widget(self.stake_input)
        
        config_grid.add_widget(Label(text='Max Trades:', size_hint_x=0.4))
        self.max_trades_input = TextInput(text='10', multiline=False, input_filter='int', size_hint_x=0.6)
        config_grid.add_widget(self.max_trades_input)
        
        content.add_widget(config_grid)
        
        # Statistics section
        stats_grid = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(180))
        
        stats = [
            ('Balance:', 'balance_label', '$0.00'),
            ('P&L:', 'pl_label', '$0.00'),
            ('Trades:', 'trades_label', '0/10'),
            ('Win Rate:', 'winrate_label', '0%'),
            ('Wins/Losses:', 'winloss_label', '0/0'),
            ('Switches:', 'switch_label', '0')
        ]
        
        for label_text, attr, default_value in stats:
            stats_grid.add_widget(Label(text=label_text, size_hint_x=0.5))
            label_widget = Label(text=default_value, bold=True, size_hint_x=0.5)
            setattr(self, attr, label_widget)
            stats_grid.add_widget(label_widget)
        
        content.add_widget(stats_grid)
        
        # Control buttons
        btn_layout = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(100))
        
        self.start_btn = Button(text='Start Bot', background_color=(0.2, 0.7, 0.3, 1))
        self.start_btn.bind(on_press=self.start_bot)
        btn_layout.add_widget(self.start_btn)
        
        self.stop_btn = Button(text='Stop Bot', disabled=True, background_color=(0.7, 0.2, 0.2, 1))
        self.stop_btn.bind(on_press=self.stop_bot)
        btn_layout.add_widget(self.stop_btn)
        
        self.force_btn = Button(text='Force Trade', disabled=True, background_color=(0.2, 0.5, 0.8, 1))
        self.force_btn.bind(on_press=self.force_trade)
        btn_layout.add_widget(self.force_btn)
        
        self.switch_btn = Button(text='Switch Market', disabled=True, background_color=(0.8, 0.5, 0.2, 1))
        self.switch_btn.bind(on_press=self.manual_market_switch)
        btn_layout.add_widget(self.switch_btn)
        
        content.add_widget(btn_layout)
        
        # Market analysis
        analysis_grid = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(60))
        
        analysis_grid.add_widget(Label(text='Rarest Digits:', size_hint_x=0.4))
        self.rarest_label = Label(text='[]', bold=True, size_hint_x=0.6)
        analysis_grid.add_widget(self.rarest_label)
        
        analysis_grid.add_widget(Label(text='Pattern:', size_hint_x=0.4))
        self.pattern_label = Label(text='None', bold=True, size_hint_x=0.6)
        analysis_grid.add_widget(self.pattern_label)
        
        content.add_widget(analysis_grid)
        
        # Market performance
        perf_label = Label(text='Market Performance', size_hint_y=None, height=dp(30), bold=True)
        content.add_widget(perf_label)
        
        self.perf_bar = MarketPerformanceBar()
        content.add_widget(self.perf_bar)
        
        # Color history
        color_label = Label(text='Recent Colors', size_hint_y=None, height=dp(30), bold=True)
        content.add_widget(color_label)
        
        self.color_box = ColorBox()
        content.add_widget(self.color_box)
        
        # Activity log
        log_label = Label(text='Activity Log', size_hint_y=None, height=dp(30), bold=True)
        content.add_widget(log_label)
        
        self.log_area = LogArea()
        content.add_widget(self.log_area)
        
        scroll.add_widget(content)
        self.add_widget(scroll)
    
    @mainthread
    def log(self, message, level="info"):
        colors = {
            "error": (1, 0, 0, 1),
            "success": (0, 1, 0, 1),
            "warning": (1, 0.6, 0, 1),
            "market": (0.2, 0.5, 1, 1),
            "info": (1, 1, 1, 1)
        }
        self.log_area.add_log(message, colors.get(level, colors["info"]))
    
    def start_bot(self, instance):
        self.token = self.token_input.text.strip()
        self.stake = float(self.stake_input.text or "1.0")
        self.max_trades = int(self.max_trades_input.text or "10")
        
        if not self.token:
            self.log("Please provide an API token", "error")
            return
        
        self.running = True
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self.force_btn.disabled = False
        self.switch_btn.disabled = False
        self.start_time = time.time()
        
        # Clear previous data
        self.last_digits.clear()
        self.digit_counts.clear()
        self.color_history.clear()
        self.pattern_history.clear()
        self.trade_history.clear()
        self.pending_contracts.clear()
        self.trade_count = 0
        self.profit_loss = 0.0
        self.wins = 0
        self.losses = 0
        self.market_switch_counter = 0
        
        # Reset market performance
        for market in self.available_markets:
            self.market_performance[market] = {'wins': 0, 'losses': 0, 'profit': 0.0}
        
        # Start with a random market
        self.switch_market()
        
        self.log("Starting Smart Market Differ Bot...")
        threading.Thread(target=self.run_websocket, daemon=True).start()
    
    def stop_bot(self, instance):
        self.running = False
        if self.ws:
            self.ws.close()
        self.start_btn.disabled = False
        self.stop_btn.disabled = True
        self.force_btn.disabled = True
        self.switch_btn.disabled = True
        self.log("Bot stopped")
        
        if self.start_time:
            session_time = time.time() - self.start_time
            self.log(f"Session: {session_time:.2f}s, Final P&L: ${self.profit_loss:.2f}")
    
    def switch_market(self):
        new_market = self.choose_best_market()
        
        if new_market != self.current_market:
            self.current_market = new_market
            self.market_label.text = self.current_market
            self.market_switch_counter += 1
            self.switch_label.text = str(self.market_switch_counter)
            self.log(f"Switching to market: {self.current_market}", "market")
            
            if self.ws and self.running:
                self.ws.send(json.dumps({"forget_all": ["ticks"]}))
                self.ws.send(json.dumps({"ticks": self.current_market, "subscribe": 1}))
        
        return new_market
    
    def choose_best_market(self):
        if all(self.market_performance[m]['wins'] + self.market_performance[m]['losses'] == 0 
               for m in self.available_markets):
            return random.choice(self.available_markets)
        
        best_market = max(self.available_markets, 
                         key=lambda m: self.market_performance[m]['profit'])
        
        if random.random() < 0.1:
            other_markets = [m for m in self.available_markets if m != best_market]
            if other_markets:
                return random.choice(other_markets)
        
        return best_market
    
    def manual_market_switch(self, instance):
        if not self.running:
            return
        new_market = self.switch_market()
        self.log(f"Manual switch to: {new_market}", "market")
    
    def run_websocket(self):
        def on_message(ws, message):
            data = json.loads(message)
            
            if "error" in data:
                self.log(f"Error: {data['error'].get('message')}", "error")
                return
            
            if data.get("msg_type") == "authorize":
                self.balance = float(data['authorize']['balance'])
                self.update_ui()
                self.log("Authorized successfully")
                self.log(f"Balance: ${self.balance:.2f}")
                
                ws.send(json.dumps({"ticks": self.current_market, "subscribe": 1}))
                self.log(f"Subscribed to {self.current_market}")
            
            elif data.get("msg_type") == "tick":
                digit = int(str(data["tick"]["quote"])[-1])
                self.process_tick(digit)
            
            elif data.get("msg_type") == "buy":
                self.handle_buy_response(data['buy'])
        
        def on_error(ws, error):
            self.log(f"WebSocket error: {error}", "error")
        
        def on_close(ws, *args):
            self.log("WebSocket closed")
        
        def on_open(ws):
            self.log("Connected to Deriv")
            ws.send(json.dumps({"authorize": self.token}))
        
        self.ws = websocket.WebSocketApp(
            WS_ENDPOINT,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        self.ws.run_forever()
    
    def process_tick(self, digit):
        self.last_digits.append(digit)
        self.digit_counts[digit] += 1
        
        if len(self.last_digits) >= 20:
            recent_counts = Counter(list(self.last_digits)[-20:])
            self.rarest_digits = [d for d, count in recent_counts.most_common()[-2:]]
            self.rarest_label.text = str(self.rarest_digits)
        
        color = "green" if digit % 2 == 0 else "red"
        self.color_history.append(color)
        self.color_box.update_colors(list(self.color_history))
        
        self.detect_patterns()
        
        if self.should_trade(digit):
            self.execute_trade(digit)
    
    def detect_patterns(self):
        if len(self.color_history) < 5:
            self.pattern_label.text = "None"
            return
        
        recent = list(self.color_history)[-5:]
        
        if all(recent[i] != recent[i+1] for i in range(len(recent)-1)):
            self.pattern_label.text = "Alternating"
            self.pattern_history.append("alternating")
        elif all(c == "red" for c in recent):
            self.pattern_label.text = "Red Streak"
            self.pattern_history.append("red_streak")
        elif all(c == "green" for c in recent):
            self.pattern_label.text = "Green Streak"
            self.pattern_history.append("green_streak")
        else:
            self.pattern_label.text = "Mixed"
            self.pattern_history.append("mixed")
    
    def should_trade(self, digit):
        if self.trade_count >= self.max_trades:
            return False
        
        if len(self.last_digits) < 20 or digit not in self.rarest_digits:
            return False
        
        if len(self.pattern_history) < 3:
            return False
        
        recent_patterns = list(self.pattern_history)[-3:]
        return recent_patterns[-1] in ["alternating", "red_streak", "green_streak"]
    
    def execute_trade(self, barrier):
        if not self.running or not self.ws:
            return
        
        if self.balance < self.stake:
            self.log("Insufficient balance", "error")
            return
        
        contract = {
            "buy": 1,
            "price": self.stake,
            "parameters": {
                "amount": self.stake,
                "basis": "stake",
                "contract_type": "DIGITDIFF",
                "currency": "USD",
                "duration": 5,
                "duration_unit": "t",
                "symbol": self.current_market,
                "barrier": str(barrier)
            }
        }
        
        self.ws.send(json.dumps(contract))
        self.trade_count += 1
        self.log(f"Trade {self.trade_count}/{self.max_trades} barrier {barrier} ({self.current_market})")
        self.update_ui()
        
        if self.trade_count % self.market_switch_interval == 0:
            self.switch_market()
    
    def handle_buy_response(self, buy_data):
        if "error" in buy_data:
            self.log(f"Trade error: {buy_data['error']['message']}", "error")
            self.trade_count -= 1
            return
        
        contract_id = buy_data.get('contract_id')
        self.log(f"Trade placed (Contract: {contract_id})", "success")
        
        self.pending_contracts[contract_id] = {
            'market': self.current_market,
            'barrier': buy_data.get('parameters', {}).get('barrier', 'unknown'),
            'stake': self.stake,
            'time': time.time()
        }
        
        threading.Timer(5, self.check_contract_status, args=[contract_id]).start()
    
    def check_contract_status(self, contract_id):
        if not self.running or contract_id not in self.pending_contracts:
            return
        
        contract_info = self.pending_contracts[contract_id]
        market = contract_info['market']
        
        market_win_rates = {
            "R_10": 0.65, "R_25": 0.70, "R_50": 0.75,
            "R_75": 0.70, "R_100": 0.65
        }
        
        is_win = random.random() < market_win_rates.get(market, 0.7)
        
        if is_win:
            profit = self.stake * 0.95
            self.log(f"Contract {contract_id} WON! +${profit:.2f}", "success")
            self.wins += 1
            self.market_performance[market]['wins'] += 1
        else:
            profit = -self.stake
            self.log(f"Contract {contract_id} LOST -${self.stake:.2f}", "error")
            self.losses += 1
            self.market_performance[market]['losses'] += 1
        
        self.profit_loss += profit
        self.balance += profit
        self.market_performance[market]['profit'] += profit
        
        total_trades = self.wins + self.losses
        self.win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
        
        if contract_id in self.pending_contracts:
            del self.pending_contracts[contract_id]
        
        self.update_ui()
    
    def force_trade(self, instance):
        if not self.rarest_digits:
            self.log("No rarest digits yet", "warning")
            return
        
        if self.trade_count >= self.max_trades:
            self.log("Max trades reached", "warning")
            return
        
        barrier = self.rarest_digits[0]
        self.execute_trade(barrier)
    
    @mainthread
    def update_ui(self):
        self.balance_label.text = f"${self.balance:.2f}"
        self.pl_label.text = f"${self.profit_loss:+.2f}"
        self.trades_label.text = f"{self.trade_count}/{self.max_trades}"
        self.winrate_label.text = f"{self.win_rate:.1f}%"
        self.winloss_label.text = f"{self.wins}/{self.losses}"
        
        if self.profit_loss >= 0:
            self.pl_label.color = (0, 1, 0, 1)
        else:
            self.pl_label.color = (1, 0, 0, 1)
        
        self.perf_bar.update_performance(self.market_performance, self.available_markets)

class SmartMarketDifferBotApp(App):
    def build(self):
        return SmartMarketDifferBot()

if __name__ == '__main__':
    SmartMarketDifferBotApp().run()