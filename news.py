#!/usr/bin/env python3
"""
Modern Smart News Analyzer GUI
A beautiful, modern GUI application for news analysis with advanced features.

Features:
- Modern dark theme UI with glassmorphism effects
- Real-time news fetching with advanced search
- Sentiment analysis with visual indicators
- Category-based news filtering
- Interactive charts and visualizations
- Bookmark and save articles
- Export functionality
- Advanced search with filters
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
import json
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import threading
import webbrowser
from typing import List, Dict, Optional
import os
from dotenv import load_dotenv
import re
from collections import Counter

# Load environment variables
load_dotenv()

# Try to import optional dependencies
try:
    from textblob import TextBlob
    HAS_TEXTBLOB = True
except ImportError:
    HAS_TEXTBLOB = False

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import seaborn as sns
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

class NewsArticle:
    """Data class for news articles"""
    def __init__(self, title, description, url, source, published_at, 
                 image_url=None, content=None):
        self.title = title
        self.description = description
        self.url = url
        self.source = source
        self.published_at = published_at
        self.image_url = image_url
        self.content = content
        self.sentiment_score = 0.0
        self.sentiment_label = "neutral"
        self.keywords = []

class NewsAnalyzer:
    """Core news analysis functionality"""
    
    def __init__(self, db_path: str = "news_analysis.db"):
        self.db_path = db_path
        self.setup_database()
        
    def setup_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                content TEXT,
                url TEXT UNIQUE,
                source TEXT,
                published_at TIMESTAMP,
                image_url TEXT,
                sentiment_score REAL DEFAULT 0.0,
                sentiment_label TEXT DEFAULT 'neutral',
                keywords TEXT,
                category TEXT,
                bookmarked INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT,
                category TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def fetch_news(self, api_key: str, query: str = None, category: str = None, 
                  country: str = "us", page_size: int = 50) -> List[NewsArticle]:
        """Fetch news from News API"""
        articles = []
        
        if query:
            # Use everything endpoint for search
            url = "https://newsapi.org/v2/everything"
            params = {
                'apiKey': api_key,
                'q': query,
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': page_size,
                'from': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            }
        else:
            # Use top-headlines for category-based news
            url = "https://newsapi.org/v2/top-headlines"
            params = {
                'apiKey': api_key,
                'country': country,
                'pageSize': page_size,
                'language': 'en'
            }
            if category and category != "all":
                params['category'] = category
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') != 'ok':
                raise Exception(f"API Error: {data.get('message', 'Unknown error')}")
            
            for item in data.get('articles', []):
                if item.get('title') and item.get('title') != '[Removed]':
                    article = NewsArticle(
                        title=item['title'],
                        description=item.get('description', ''),
                        url=item['url'],
                        source=item['source']['name'],
                        published_at=datetime.fromisoformat(item['publishedAt'].replace('Z', '+00:00')),
                        image_url=item.get('urlToImage'),
                        content=item.get('content', '')
                    )
                    articles.append(article)
            
            return articles
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error: {str(e)}")
        except Exception as e:
            raise Exception(f"Error fetching news: {str(e)}")
    
    def analyze_sentiment(self, text: str) -> tuple:
        """Analyze sentiment using TextBlob"""
        if not HAS_TEXTBLOB or not text:
            return 0.0, "neutral"
        
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
            
            if polarity > 0.1:
                label = "positive"
            elif polarity < -0.1:
                label = "negative"
            else:
                label = "neutral"
            
            return polarity, label
        except:
            return 0.0, "neutral"
    
    def extract_keywords(self, text: str, num_keywords: int = 5) -> List[str]:
        """Extract keywords from text"""
        if not text:
            return []
        
        # Clean text
        text = re.sub(r'[^a-zA-Z\s]', '', text.lower())
        
        # Stop words
        stop_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before',
            'after', 'above', 'below', 'between', 'among', 'this', 'that', 'these',
            'those', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have',
            'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
            'may', 'might', 'must', 'can', 'said', 'says', 'news', 'report'
        }
        
        words = [word for word in text.split() if len(word) >= 3 and word not in stop_words]
        word_freq = Counter(words)
        return [word for word, _ in word_freq.most_common(num_keywords)]
    
    def process_article(self, article: NewsArticle) -> NewsArticle:
        """Process article with sentiment analysis and keyword extraction"""
        full_text = f"{article.title} {article.description}"
        article.sentiment_score, article.sentiment_label = self.analyze_sentiment(full_text)
        article.keywords = self.extract_keywords(full_text)
        return article
    
    def save_articles(self, articles: List[NewsArticle], category: str = None):
        """Save articles to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        saved_count = 0
        for article in articles:
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO articles 
                    (title, description, content, url, source, published_at, image_url,
                     sentiment_score, sentiment_label, keywords, category)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    article.title,
                    article.description,
                    article.content,
                    article.url,
                    article.source,
                    article.published_at.isoformat(),
                    article.image_url,
                    article.sentiment_score,
                    article.sentiment_label,
                    ','.join(article.keywords),
                    category or 'general'
                ))
                saved_count += 1
            except sqlite3.IntegrityError:
                continue
        
        conn.commit()
        conn.close()
        return saved_count

class ModernNewsGUI:
    """Modern GUI for the News Analyzer"""
    
    def __init__(self, root):
        self.root = root
        self.analyzer = NewsAnalyzer()
        self.current_articles = []
        self.is_loading = False

        # Initialize API key before GUI setup
        self.api_key = os.getenv('NEWS_API_KEY')
        self.setup_gui()

        # Show API key dialog if not set
        if not self.api_key:
            self.show_api_key_dialog()
    
    def setup_styles(self):
        """Setup modern styling"""
        style = ttk.Style()
        
        # Configure colors - Modern dark theme
        self.colors = {
            'bg_primary': '#0F0F23',      # Deep dark blue
            'bg_secondary': '#16213E',     # Slightly lighter dark blue
            'bg_accent': '#1A2B4C',       # Accent blue
            'text_primary': '#FFFFFF',     # White text
            'text_secondary': '#B8BCC8',   # Light gray text
            'accent': '#4A90E2',          # Bright blue accent
            'success': '#00D4AA',         # Green
            'warning': '#FFB946',         # Orange
            'error': '#FF6B6B',           # Red
            'positive': '#00C851',        # Positive sentiment
            'negative': '#FF4444',        # Negative sentiment
            'neutral': '#757575'          # Neutral sentiment
        }
        
        # Configure root
        self.root.configure(bg=self.colors['bg_primary'])
        
        # Configure ttk styles
        style.theme_use('clam')
        
        # Configure notebook (tabs)
        style.configure('Custom.TNotebook', 
                       background=self.colors['bg_primary'],
                       borderwidth=0)
        style.configure('Custom.TNotebook.Tab',
                       background=self.colors['bg_secondary'],
                       foreground=self.colors['text_secondary'],
                       padding=[20, 10],
                       borderwidth=0)
        style.map('Custom.TNotebook.Tab',
                 background=[('selected', self.colors['accent']),
                           ('active', self.colors['bg_accent'])],
                 foreground=[('selected', self.colors['text_primary'])])
        
        # Configure frames
        style.configure('Custom.TFrame',
                       background=self.colors['bg_primary'])
        style.configure('Secondary.TFrame',
                       background=self.colors['bg_secondary'])
        style.configure('Accent.TFrame',
                       background=self.colors['bg_accent'])
        
        # Configure buttons
        style.configure('Custom.TButton',
                       background=self.colors['accent'],
                       foreground=self.colors['text_primary'],
                       borderwidth=0,
                       padding=[15, 10])
        style.map('Custom.TButton',
                 background=[('active', '#3A7BD5'),
                           ('pressed', '#2E6BCF')])
        
        # Configure labels
        style.configure('Title.TLabel',
                       background=self.colors['bg_primary'],
                       foreground=self.colors['text_primary'],
                       font=('Helvetica', 16, 'bold'))
        style.configure('Heading.TLabel',
                       background=self.colors['bg_primary'],
                       foreground=self.colors['text_primary'],
                       font=('Helvetica', 12, 'bold'))
        style.configure('Custom.TLabel',
                       background=self.colors['bg_primary'],
                       foreground=self.colors['text_secondary'],
                       font=('Helvetica', 9))
        
        # Configure entries and comboboxes
        style.configure('Custom.TEntry',
                       fieldbackground=self.colors['bg_secondary'],
                       foreground=self.colors['text_primary'],
                       borderwidth=1,
                       insertcolor=self.colors['text_primary'])
        
        style.configure('Custom.TCombobox',
                       fieldbackground=self.colors['bg_secondary'],
                       foreground=self.colors['text_primary'],
                       background=self.colors['bg_secondary'])
    
    def setup_gui(self):
        """Setup the main GUI"""
        self.setup_styles()  # <-- Move this to the top!
        self.root.title("Smart News Analyzer")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)
        
        # Create main container
        main_frame = ttk.Frame(self.root, style='Custom.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create header
        self.create_header(main_frame)
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(main_frame, style='Custom.TNotebook')
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(20, 0))
        
        # Create tabs
        self.create_news_tab()
        self.create_search_tab()
        self.create_analytics_tab()
        self.create_bookmarks_tab()
        self.create_settings_tab()
    
    def create_header(self, parent):
        """Create the header section"""
        header_frame = ttk.Frame(parent, style='Accent.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Title
        title_label = ttk.Label(header_frame, text="📰 Smart News Analyzer",
                               style='Title.TLabel', font=('Helvetica', 20, 'bold'))
        title_label.pack(side=tk.LEFT, padx=20, pady=15)
        
        # Status indicator
        self.status_frame = ttk.Frame(header_frame, style='Accent.TFrame')
        self.status_frame.pack(side=tk.RIGHT, padx=20, pady=15)
        
        self.status_label = ttk.Label(self.status_frame, text="Ready",
                                     style='Custom.TLabel')
        self.status_label.pack(side=tk.RIGHT)
        
        # Loading indicator
        self.loading_label = ttk.Label(self.status_frame, text="⟳ Loading...",
                                      style='Custom.TLabel')
    
    def create_news_tab(self):
        """Create the main news tab"""
        news_frame = ttk.Frame(self.notebook, style='Custom.TFrame')
        self.notebook.add(news_frame, text="Latest News")
        
        # Top controls
        control_frame = ttk.Frame(news_frame, style='Secondary.TFrame')
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Category selection
        ttk.Label(control_frame, text="Category:", style='Heading.TLabel').pack(side=tk.LEFT, padx=(10, 5))
        
        self.category_var = tk.StringVar(value="general")
        categories = ["all", "general", "business", "entertainment", "health", 
                     "science", "sports", "technology"]
        category_combo = ttk.Combobox(control_frame, textvariable=self.category_var,
                                     values=categories, style='Custom.TCombobox', width=15)
        category_combo.pack(side=tk.LEFT, padx=(0, 20))
        
        # Refresh button
        refresh_btn = ttk.Button(control_frame, text="🔄 Refresh News",
                               command=self.refresh_news, style='Custom.TButton')
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # Articles count
        self.articles_count_label = ttk.Label(control_frame, text="0 articles loaded",
                                            style='Custom.TLabel')
        self.articles_count_label.pack(side=tk.RIGHT, padx=10)
        
        # Create scrollable news feed
        self.create_news_feed(news_frame)
    
    def create_search_tab(self):
        """Create the advanced search tab"""
        search_frame = ttk.Frame(self.notebook, style='Custom.TFrame')
        self.notebook.add(search_frame, text="Advanced Search")
        
        # Search controls
        search_control_frame = ttk.Frame(search_frame, style='Secondary.TFrame')
        search_control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Search query
        ttk.Label(search_control_frame, text="Search Query:", style='Heading.TLabel').pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        search_entry_frame = ttk.Frame(search_control_frame, style='Secondary.TFrame')
        search_entry_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_entry_frame, textvariable=self.search_var,
                               style='Custom.TEntry', font=('Helvetica', 11))
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        search_btn = ttk.Button(search_entry_frame, text="🔍 Search",
                              command=self.search_news, style='Custom.TButton')
        search_btn.pack(side=tk.RIGHT)
        
        # Search filters
        filters_frame = ttk.Frame(search_control_frame, style='Secondary.TFrame')
        filters_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        # Date range
        ttk.Label(filters_frame, text="Date Range:", style='Custom.TLabel').pack(side=tk.LEFT, padx=(0, 10))
        
        self.date_range_var = tk.StringVar(value="week")
        date_options = ["today", "week", "month"]
        date_combo = ttk.Combobox(filters_frame, textvariable=self.date_range_var,
                                values=date_options, style='Custom.TCombobox', width=10)
        date_combo.pack(side=tk.LEFT, padx=(0, 20))
        
        # Sort by
        ttk.Label(filters_frame, text="Sort by:", style='Custom.TLabel').pack(side=tk.LEFT, padx=(0, 10))
        
        self.sort_var = tk.StringVar(value="publishedAt")
        sort_options = ["publishedAt", "relevancy", "popularity"]
        sort_combo = ttk.Combobox(filters_frame, textvariable=self.sort_var,
                                values=sort_options, style='Custom.TCombobox', width=12)
        sort_combo.pack(side=tk.LEFT)
        
        # Recent searches
        recent_frame = ttk.Frame(search_frame, style='Secondary.TFrame')
        recent_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Label(recent_frame, text="Recent Searches:", style='Heading.TLabel').pack(anchor=tk.W, padx=10, pady=5)
        
        self.recent_searches_frame = ttk.Frame(recent_frame, style='Secondary.TFrame')
        self.recent_searches_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        # Search results
        self.create_search_results(search_frame)
        
        # Load recent searches
        self.load_recent_searches()
    
    def create_analytics_tab(self):
        """Create the analytics tab"""
        analytics_frame = ttk.Frame(self.notebook, style='Custom.TFrame')
        self.notebook.add(analytics_frame, text="Analytics")
        
        # Analytics controls
        analytics_control_frame = ttk.Frame(analytics_frame, style='Secondary.TFrame')
        analytics_control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(analytics_control_frame, text="📊 Generate Report",
                  command=self.generate_analytics, style='Custom.TButton').pack(side=tk.LEFT, padx=10)
        
        ttk.Button(analytics_control_frame, text="📈 Export Data",
                  command=self.export_data, style='Custom.TButton').pack(side=tk.LEFT, padx=5)
        
        # Analytics display area
        self.analytics_display = ttk.Frame(analytics_frame, style='Custom.TFrame')
        self.analytics_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Default analytics message
        default_label = ttk.Label(self.analytics_display, 
                                text="Click 'Generate Report' to view analytics",
                                style='Custom.TLabel', font=('Helvetica', 12))
        default_label.pack(expand=True)
    
    def create_bookmarks_tab(self):
        """Create the bookmarks tab"""
        bookmarks_frame = ttk.Frame(self.notebook, style='Custom.TFrame')
        self.notebook.add(bookmarks_frame, text="Bookmarks")
        
        # Bookmarks controls
        bookmarks_control_frame = ttk.Frame(bookmarks_frame, style='Secondary.TFrame')
        bookmarks_control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(bookmarks_control_frame, text="🔄 Refresh",
                  command=self.load_bookmarks, style='Custom.TButton').pack(side=tk.LEFT, padx=10)
        
        ttk.Button(bookmarks_control_frame, text="🗑️ Clear All",
                  command=self.clear_bookmarks, style='Custom.TButton').pack(side=tk.LEFT, padx=5)
        
        self.bookmarks_count_label = ttk.Label(bookmarks_control_frame, text="0 bookmarks",
                                             style='Custom.TLabel')
        self.bookmarks_count_label.pack(side=tk.RIGHT, padx=10)
        
        # Bookmarks display
        self.create_bookmarks_display(bookmarks_frame)
        self.load_bookmarks()
    
    def create_settings_tab(self):
        """Create the settings tab"""
        settings_frame = ttk.Frame(self.notebook, style='Custom.TFrame')
        self.notebook.add(settings_frame, text="Settings")
        
        # API Key section
        api_section = ttk.Frame(settings_frame, style='Secondary.TFrame')
        api_section.pack(fill=tk.X, padx=20, pady=20)
        
        ttk.Label(api_section, text="News API Configuration", 
                 style='Heading.TLabel', font=('Helvetica', 14, 'bold')).pack(anchor=tk.W, pady=(10, 5))
        
        ttk.Label(api_section, text="API Key:", style='Custom.TLabel').pack(anchor=tk.W, pady=(10, 2))
        
        api_frame = ttk.Frame(api_section, style='Secondary.TFrame')
        api_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.api_key_var = tk.StringVar(value=self.api_key or "")
        api_entry = ttk.Entry(api_frame, textvariable=self.api_key_var,
                            style='Custom.TEntry', show="*", width=50)
        api_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(api_frame, text="Save", command=self.save_api_key,
                  style='Custom.TButton').pack(side=tk.LEFT, padx=5)
        
        ttk.Button(api_frame, text="Get API Key", command=self.open_newsapi_website,
                  style='Custom.TButton').pack(side=tk.LEFT, padx=5)
        
        # App info section
        info_section = ttk.Frame(settings_frame, style='Secondary.TFrame')
        info_section.pack(fill=tk.X, padx=20, pady=20)
        
        ttk.Label(info_section, text="Application Information", 
                 style='Heading.TLabel', font=('Helvetica', 14, 'bold')).pack(anchor=tk.W, pady=(10, 5))
        
        info_text = """
Smart News Analyzer v2.0
A modern GUI application for news analysis and sentiment tracking.

Features:
• Real-time news fetching from multiple sources
• Advanced sentiment analysis
• Interactive visualizations and analytics
• Bookmark management
• Export capabilities

Dependencies Status:
"""
        
        ttk.Label(info_section, text=info_text, style='Custom.TLabel',
                 justify=tk.LEFT).pack(anchor=tk.W, pady=10)
        
        # Dependency status
        deps_status = f"• TextBlob (Sentiment Analysis): {'✅ Available' if HAS_TEXTBLOB else '❌ Not Available'}\n"
        deps_status += f"• Matplotlib (Visualizations): {'✅ Available' if HAS_MATPLOTLIB else '❌ Not Available'}"
        
        ttk.Label(info_section, text=deps_status, style='Custom.TLabel',
                 justify=tk.LEFT).pack(anchor=tk.W)
    
    def create_news_feed(self, parent):
        """Create scrollable news feed"""
        # Create canvas and scrollbar
        canvas_frame = ttk.Frame(parent, style='Custom.TFrame')
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        canvas = tk.Canvas(canvas_frame, bg=self.colors['bg_primary'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        self.news_feed_frame = ttk.Frame(canvas, style='Custom.TFrame')
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.news_feed_frame, anchor="nw")
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.news_canvas = canvas
        
        # Mouse wheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", on_mousewheel)
    
    def create_search_results(self, parent):
        """Create search results display"""
        results_frame = ttk.Frame(parent, style='Custom.TFrame')
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Results header
        self.search_results_header = ttk.Label(results_frame, text="Enter a search query above",
                                              style='Custom.TLabel', font=('Helvetica', 12))
        self.search_results_header.pack(pady=20)
        
        # Results canvas
        canvas_frame = ttk.Frame(results_frame, style='Custom.TFrame')
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(canvas_frame, bg=self.colors['bg_primary'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        self.search_results_frame = ttk.Frame(canvas, style='Custom.TFrame')
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.search_results_frame, anchor="nw")
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.search_canvas = canvas
        
        # Mouse wheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", on_mousewheel)
    
    def create_bookmarks_display(self, parent):
        """Create bookmarks display"""
        canvas_frame = ttk.Frame(parent, style='Custom.TFrame')
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        canvas = tk.Canvas(canvas_frame, bg=self.colors['bg_primary'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        self.bookmarks_frame = ttk.Frame(canvas, style='Custom.TFrame')
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.bookmarks_frame, anchor="nw")
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.bookmarks_canvas = canvas
        
        # Mouse wheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", on_mousewheel)
    
    def create_article_card(self, article, parent, show_bookmark=True):
        """Create a modern article card"""
        # Main card frame with border effect
        card_frame = tk.Frame(parent, bg=self.colors['bg_secondary'], relief='flat', bd=0)
        card_frame.pack(fill=tk.X, padx=5, pady=8)
        
        # Add hover effect
        def on_enter(e):
            card_frame.configure(bg=self.colors['bg_accent'])
        
        def on_leave(e):
            card_frame.configure(bg=self.colors['bg_secondary'])
        
        card_frame.bind("<Enter>", on_enter)
        card_frame.bind("<Leave>", on_leave)
        
        # Inner padding frame
        inner_frame = tk.Frame(card_frame, bg=self.colors['bg_secondary'])
        inner_frame.pack(fill=tk.X, padx=15, pady=12)
        
        # Header with source and sentiment
        header_frame = tk.Frame(inner_frame, bg=self.colors['bg_secondary'])
        header_frame.pack(fill=tk.X, pady=(0, 8))
        
        # Source and date
        source_text = f"📰 {article.source}"
        if hasattr(article, 'published_at') and article.published_at:
            time_diff = datetime.now() - article.published_at.replace(tzinfo=None)
            if time_diff.days > 0:
                time_str = f"{time_diff.days}d ago"
            elif time_diff.seconds > 3600:
                time_str = f"{time_diff.seconds // 3600}h ago"
            else:
                time_str = f"{time_diff.seconds // 60}m ago"
            source_text += f" • {time_str}"
        
        source_label = tk.Label(header_frame, text=source_text, 
                               bg=self.colors['bg_secondary'], fg=self.colors['text_secondary'],
                               font=('Helvetica', 9))
        source_label.pack(side=tk.LEFT)
        
        # Sentiment indicator
        sentiment_color = self.colors['neutral']
        sentiment_icon = "😐"
        if hasattr(article, 'sentiment_label'):
            if article.sentiment_label == 'positive':
                sentiment_color = self.colors['positive']
                sentiment_icon = "😊"
            elif article.sentiment_label == 'negative':
                sentiment_color = self.colors['negative']
                sentiment_icon = "😞"
        
        sentiment_label = tk.Label(header_frame, text=f"{sentiment_icon} {article.sentiment_label.capitalize()}" if hasattr(article, 'sentiment_label') else "",
                                  bg=self.colors['bg_secondary'], fg=sentiment_color,
                                  font=('Helvetica', 9, 'bold'))
        sentiment_label.pack(side=tk.RIGHT)
        
        # Title
        title_label = tk.Label(inner_frame, text=article.title,
                              bg=self.colors['bg_secondary'], fg=self.colors['text_primary'],
                              font=('Helvetica', 11, 'bold'), wraplength=800, justify=tk.LEFT)
        title_label.pack(anchor=tk.W, pady=(0, 5))
        
        # Description
        if article.description:
            desc_text = article.description[:200] + "..." if len(article.description) > 200 else article.description
            desc_label = tk.Label(inner_frame, text=desc_text,
                                 bg=self.colors['bg_secondary'], fg=self.colors['text_secondary'],
                                 font=('Helvetica', 9), wraplength=800, justify=tk.LEFT)
            desc_label.pack(anchor=tk.W, pady=(0, 8))
        
        # Keywords
        if hasattr(article, 'keywords') and article.keywords:
            keywords_text = "🏷️ " + " • ".join(article.keywords[:5])
            keywords_label = tk.Label(inner_frame, text=keywords_text,
                                     bg=self.colors['bg_secondary'], fg=self.colors['accent'],
                                     font=('Helvetica', 8))
            keywords_label.pack(anchor=tk.W, pady=(0, 8))
        
        # Action buttons
        actions_frame = tk.Frame(inner_frame, bg=self.colors['bg_secondary'])
        actions_frame.pack(fill=tk.X)
        
        # Read button
        read_btn = tk.Button(actions_frame, text="📖 Read Full Article",
                            command=lambda: self.open_article(article.url),
                            bg=self.colors['accent'], fg=self.colors['text_primary'],
                            font=('Helvetica', 8, 'bold'), relief='flat', padx=10, pady=5,
                            cursor='hand2')
        read_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Bookmark button
        if show_bookmark:
            bookmark_btn = tk.Button(actions_frame, text="🔖 Bookmark",
                                   command=lambda: self.toggle_bookmark(article),
                                   bg=self.colors['bg_accent'], fg=self.colors['text_secondary'],
                                   font=('Helvetica', 8), relief='flat', padx=10, pady=5,
                                   cursor='hand2')
            bookmark_btn.pack(side=tk.LEFT)
        
        return card_frame
    
    def show_loading(self, message="Loading..."):
        """Show loading indicator"""
        self.is_loading = True
        self.loading_label.configure(text=f"⟳ {message}")
        self.loading_label.pack(side=tk.RIGHT, padx=(10, 0))
        self.status_label.pack_forget()
        self.root.update()
    
    def hide_loading(self, status="Ready"):
        """Hide loading indicator"""
        self.is_loading = False
        self.loading_label.pack_forget()
        self.status_label.configure(text=status)
        self.status_label.pack(side=tk.RIGHT)
        self.root.update()
    
    def refresh_news(self):
        """Refresh news in a separate thread"""
        if self.is_loading:
            return
        
        if not self.api_key:
            messagebox.showerror("Error", "Please set your News API key in Settings")
            return
        
        def fetch_and_display():
            try:
                self.show_loading("Fetching latest news...")
                
                category = self.category_var.get()
                articles = self.analyzer.fetch_news(
                    self.api_key,
                    category=None if category == "all" else category
                )
                
                self.show_loading("Processing articles...")
                
                # Process articles
                processed_articles = []
                for article in articles:
                    processed_article = self.analyzer.process_article(article)
                    processed_articles.append(processed_article)
                
                # Save to database
                saved_count = self.analyzer.save_articles(processed_articles, category)
                
                # Update UI in main thread
                self.root.after(0, self.display_articles, processed_articles)
                self.root.after(0, self.hide_loading, f"Loaded {len(processed_articles)} articles")
                
            except Exception as e:
                self.root.after(0, self.hide_loading, "Error")
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to fetch news: {str(e)}"))
        
        # Run in separate thread
        threading.Thread(target=fetch_and_display, daemon=True).start()
    
    def search_news(self):
        """Search news with query"""
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Warning", "Please enter a search query")
            return
        
        if not self.api_key:
            messagebox.showerror("Error", "Please set your News API key in Settings")
            return
        
        def search_and_display():
            try:
                self.show_loading(f"Searching for '{query}'...")
                
                articles = self.analyzer.fetch_news(
                    self.api_key,
                    query=query
                )
                
                self.show_loading("Processing search results...")
                
                # Process articles
                processed_articles = []
                for article in articles:
                    processed_article = self.analyzer.process_article(article)
                    processed_articles.append(processed_article)
                
                # Save search query
                self.save_search_query(query)
                
                # Update UI in main thread
                self.root.after(0, self.display_search_results, processed_articles, query)
                self.root.after(0, self.hide_loading, f"Found {len(processed_articles)} articles")
                
            except Exception as e:
                self.root.after(0, self.hide_loading, "Error")
                self.root.after(0, lambda: messagebox.showerror("Error", f"Search failed: {str(e)}"))
        
        # Run in separate thread
        threading.Thread(target=search_and_display, daemon=True).start()
    
    def display_articles(self, articles):
        """Display articles in the news feed"""
        # Clear existing articles
        for widget in self.news_feed_frame.winfo_children():
            widget.destroy()
        
        self.current_articles = articles
        
        if not articles:
            no_articles_label = tk.Label(self.news_feed_frame, 
                                        text="No articles found. Try refreshing or check your internet connection.",
                                        bg=self.colors['bg_primary'], fg=self.colors['text_secondary'],
                                        font=('Helvetica', 12))
            no_articles_label.pack(expand=True, pady=50)
        else:
            for article in articles:
                self.create_article_card(article, self.news_feed_frame)
        
        # Update articles count
        self.articles_count_label.configure(text=f"{len(articles)} articles loaded")
        
        # Update canvas scroll region
        self.news_feed_frame.update_idletasks()
        self.news_canvas.configure(scrollregion=self.news_canvas.bbox("all"))
    
    def display_search_results(self, articles, query):
        """Display search results"""
        # Clear existing results
        for widget in self.search_results_frame.winfo_children():
            widget.destroy()
        
        # Update header
        self.search_results_header.configure(text=f"Search results for '{query}' ({len(articles)} found)")
        
        if not articles:
            no_results_label = tk.Label(self.search_results_frame,
                                       text="No articles found for your search query. Try different keywords.",
                                       bg=self.colors['bg_primary'], fg=self.colors['text_secondary'],
                                       font=('Helvetica', 12))
            no_results_label.pack(expand=True, pady=50)
        else:
            for article in articles:
                self.create_article_card(article, self.search_results_frame)
        
        # Update canvas scroll region
        self.search_results_frame.update_idletasks()
        self.search_canvas.configure(scrollregion=self.search_canvas.bbox("all"))
        
        # Load recent searches
        self.load_recent_searches()
    
    def save_search_query(self, query):
        """Save search query to database"""
        try:
            conn = sqlite3.connect(self.analyzer.db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO searches (query) VALUES (?)", (query,))
            conn.commit()
            conn.close()
        except:
            pass
    
    def load_recent_searches(self):
        """Load and display recent searches"""
        # Clear existing buttons
        for widget in self.recent_searches_frame.winfo_children():
            widget.destroy()
        
        try:
            conn = sqlite3.connect(self.analyzer.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT query FROM searches ORDER BY timestamp DESC LIMIT 5")
            searches = cursor.fetchall()
            conn.close()
            
            for i, (query,) in enumerate(searches):
                btn = tk.Button(self.recent_searches_frame, text=query,
                              command=lambda q=query: self.set_search_query(q),
                              bg=self.colors['bg_accent'], fg=self.colors['text_primary'],
                              font=('Helvetica', 8), relief='flat', padx=8, pady=3,
                              cursor='hand2')
                btn.pack(side=tk.LEFT, padx=(0, 5))
        except:
            pass
    
    def set_search_query(self, query):
        """Set search query from recent searches"""
        self.search_var.set(query)
    
    def toggle_bookmark(self, article):
        """Toggle bookmark for article"""
        try:
            conn = sqlite3.connect(self.analyzer.db_path)
            cursor = conn.cursor()
            
            # Check if already bookmarked
            cursor.execute("SELECT bookmarked FROM articles WHERE url = ?", (article.url,))
            result = cursor.fetchone()
            
            if result:
                new_bookmark_state = 1 - result[0]  # Toggle between 0 and 1
                cursor.execute("UPDATE articles SET bookmarked = ? WHERE url = ?", 
                             (new_bookmark_state, article.url))
                action = "added to" if new_bookmark_state else "removed from"
                messagebox.showinfo("Bookmark", f"Article {action} bookmarks!")
            else:
                # Article not in database, add it
                processed_article = self.analyzer.process_article(article)
                cursor.execute("""
                    INSERT INTO articles 
                    (title, description, content, url, source, published_at, image_url,
                     sentiment_score, sentiment_label, keywords, bookmarked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    processed_article.title,
                    processed_article.description,
                    processed_article.content or '',
                    processed_article.url,
                    processed_article.source,
                    processed_article.published_at.isoformat(),
                    processed_article.image_url,
                    processed_article.sentiment_score,
                    processed_article.sentiment_label,
                    ','.join(processed_article.keywords)
                ))
                messagebox.showinfo("Bookmark", "Article added to bookmarks!")
            
            conn.commit()
            conn.close()
            
            # Refresh bookmarks if on bookmarks tab
            if self.notebook.index(self.notebook.select()) == 3:  # Bookmarks tab
                self.load_bookmarks()
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to bookmark article: {str(e)}")
    
    def load_bookmarks(self):
        """Load bookmarked articles"""
        # Clear existing bookmarks
        for widget in self.bookmarks_frame.winfo_children():
            widget.destroy()
        
        try:
            conn = sqlite3.connect(self.analyzer.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT title, description, url, source, published_at, 
                       sentiment_score, sentiment_label, keywords
                FROM articles 
                WHERE bookmarked = 1
                ORDER BY created_at DESC
            """)
            bookmarks = cursor.fetchall()
            conn.close()
            
            self.bookmarks_count_label.configure(text=f"{len(bookmarks)} bookmarks")
            
            if not bookmarks:
                no_bookmarks_label = tk.Label(self.bookmarks_frame,
                                            text="No bookmarked articles yet. Bookmark articles from the news feed!",
                                            bg=self.colors['bg_primary'], fg=self.colors['text_secondary'],
                                            font=('Helvetica', 12))
                no_bookmarks_label.pack(expand=True, pady=50)
            else:
                for bookmark_data in bookmarks:
                    # Create article object from database data
                    article = NewsArticle(
                        title=bookmark_data[0],
                        description=bookmark_data[1] or '',
                        url=bookmark_data[2],
                        source=bookmark_data[3],
                        published_at=datetime.fromisoformat(bookmark_data[4])
                    )
                    article.sentiment_score = bookmark_data[5]
                    article.sentiment_label = bookmark_data[6]
                    article.keywords = bookmark_data[7].split(',') if bookmark_data[7] else []
                    
                    self.create_article_card(article, self.bookmarks_frame, show_bookmark=False)
            
            # Update canvas scroll region
            self.bookmarks_frame.update_idletasks()
            self.bookmarks_canvas.configure(scrollregion=self.bookmarks_canvas.bbox("all"))
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load bookmarks: {str(e)}")
    
    def clear_bookmarks(self):
        """Clear all bookmarks"""
        if messagebox.askyesno("Confirm", "Are you sure you want to clear all bookmarks?"):
            try:
                conn = sqlite3.connect(self.analyzer.db_path)
                cursor = conn.cursor()
                cursor.execute("UPDATE articles SET bookmarked = 0 WHERE bookmarked = 1")
                conn.commit()
                conn.close()
                
                self.load_bookmarks()
                messagebox.showinfo("Success", "All bookmarks cleared!")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear bookmarks: {str(e)}")
    
    def generate_analytics(self):
        """Generate and display analytics"""
        # Clear existing analytics
        for widget in self.analytics_display.winfo_children():
            widget.destroy()
        
        try:
            conn = sqlite3.connect(self.analyzer.db_path)
            df = pd.read_sql_query("""
                SELECT sentiment_label, sentiment_score, source, created_at, keywords
                FROM articles 
                WHERE created_at >= datetime('now', '-30 days')
            """, conn)
            conn.close()
            
            if df.empty:
                no_data_label = tk.Label(self.analytics_display,
                                       text="No data available for analytics. Fetch some news first!",
                                       bg=self.colors['bg_primary'], fg=self.colors['text_secondary'],
                                       font=('Helvetica', 12))
                no_data_label.pack(expand=True)
                return
            
            # Create analytics summary
            summary_frame = ttk.Frame(self.analytics_display, style='Secondary.TFrame')
            summary_frame.pack(fill=tk.X, padx=10, pady=10)
            
            ttk.Label(summary_frame, text="Analytics Summary (Last 30 Days)",
                     style='Heading.TLabel', font=('Helvetica', 14, 'bold')).pack(pady=10)
            
            # Statistics
            stats_frame = ttk.Frame(summary_frame, style='Secondary.TFrame')
            stats_frame.pack(fill=tk.X, padx=20, pady=10)
            
            total_articles = len(df)
            avg_sentiment = df['sentiment_score'].mean()
            sentiment_dist = df['sentiment_label'].value_counts()
            
            stats_text = f"""
Total Articles Analyzed: {total_articles}
Average Sentiment Score: {avg_sentiment:.3f}
Positive Articles: {sentiment_dist.get('positive', 0)} ({sentiment_dist.get('positive', 0)/total_articles*100:.1f}%)
Negative Articles: {sentiment_dist.get('negative', 0)} ({sentiment_dist.get('negative', 0)/total_articles*100:.1f}%)
Neutral Articles: {sentiment_dist.get('neutral', 0)} ({sentiment_dist.get('neutral', 0)/total_articles*100:.1f}%)
            """
            
            stats_label = tk.Label(stats_frame, text=stats_text.strip(),
                                  bg=self.colors['bg_secondary'], fg=self.colors['text_primary'],
                                  font=('Helvetica', 10), justify=tk.LEFT)
            stats_label.pack(anchor=tk.W)
            
            # Top sources
            if 'source' in df.columns:
                sources_frame = ttk.Frame(summary_frame, style='Secondary.TFrame')
                sources_frame.pack(fill=tk.X, padx=20, pady=10)
                
                ttk.Label(sources_frame, text="Top News Sources:",
                         style='Custom.TLabel', font=('Helvetica', 11, 'bold')).pack(anchor=tk.W, pady=(10, 5))
                
                top_sources = df['source'].value_counts().head(5)
                sources_text = "\n".join([f"• {source}: {count} articles" 
                                        for source, count in top_sources.items()])
                
                sources_label = tk.Label(sources_frame, text=sources_text,
                                       bg=self.colors['bg_secondary'], fg=self.colors['text_secondary'],
                                       font=('Helvetica', 9), justify=tk.LEFT)
                sources_label.pack(anchor=tk.W)
            
            # Top keywords
            if 'keywords' in df.columns:
                all_keywords = []
                for keywords_str in df['keywords'].dropna():
                    if keywords_str:
                        all_keywords.extend(keywords_str.split(','))
                
                if all_keywords:
                    keywords_frame = ttk.Frame(summary_frame, style='Secondary.TFrame')
                    keywords_frame.pack(fill=tk.X, padx=20, pady=10)
                    
                    ttk.Label(keywords_frame, text="Top Keywords:",
                             style='Custom.TLabel', font=('Helvetica', 11, 'bold')).pack(anchor=tk.W, pady=(10, 5))
                    
                    top_keywords = Counter(all_keywords).most_common(10)
                    keywords_text = " • ".join([f"{keyword} ({count})" 
                                              for keyword, count in top_keywords])
                    
                    keywords_label = tk.Label(keywords_frame, text=keywords_text,
                                            bg=self.colors['bg_secondary'], fg=self.colors['accent'],
                                            font=('Helvetica', 9), wraplength=800, justify=tk.LEFT)
                    keywords_label.pack(anchor=tk.W)
            
        except Exception as e:
            error_label = tk.Label(self.analytics_display,
                                 text=f"Error generating analytics: {str(e)}",
                                 bg=self.colors['bg_primary'], fg=self.colors['error'],
                                 font=('Helvetica', 11))
            error_label.pack(expand=True)
    
    def export_data(self):
        """Export data to CSV"""
        try:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title="Save News Data"
            )
            
            if file_path:
                conn = sqlite3.connect(self.analyzer.db_path)
                df = pd.read_sql_query("""
                    SELECT title, description, url, source, published_at, 
                           sentiment_score, sentiment_label, keywords, category, bookmarked
                    FROM articles 
                    ORDER BY published_at DESC
                """, conn)
                conn.close()
                
                df.to_csv(file_path, index=False)
                messagebox.showinfo("Success", f"Data exported successfully to {file_path}")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export data: {str(e)}")
    
    def open_article(self, url):
        """Open article in web browser"""
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open article: {str(e)}")
    
    def show_api_key_dialog(self):
        """Show API key input dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("News API Key Required")
        dialog.geometry("500x300")
        dialog.configure(bg=self.colors['bg_primary'])
        dialog.resizable(False, False)
        dialog.grab_set()
        
        # Center the dialog
        dialog.transient(self.root)
        
        frame = tk.Frame(dialog, bg=self.colors['bg_primary'])
        frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)
        
        tk.Label(frame, text="🔑 News API Key Required",
                bg=self.colors['bg_primary'], fg=self.colors['text_primary'],
                font=('Helvetica', 16, 'bold')).pack(pady=(0, 20))
        
        tk.Label(frame, text="To use this application, you need a free API key from NewsAPI.org",
                bg=self.colors['bg_primary'], fg=self.colors['text_secondary'],
                font=('Helvetica', 11)).pack(pady=(0, 10))
        
        tk.Label(frame, text="Enter your API key:",
                bg=self.colors['bg_primary'], fg=self.colors['text_primary'],
                font=('Helvetica', 10, 'bold')).pack(anchor=tk.W, pady=(10, 5))
        
        api_entry = tk.Entry(frame, width=50, font=('Helvetica', 10))
        api_entry.pack(fill=tk.X, pady=(0, 20))
        
        button_frame = tk.Frame(frame, bg=self.colors['bg_primary'])
        button_frame.pack(fill=tk.X)
        
        def save_and_close():
            key = api_entry.get().strip()
            if key:
                self.api_key = key
                self.api_key_var.set(key)
                self.save_api_key()
                dialog.destroy()
            else:
                messagebox.showerror("Error", "Please enter a valid API key")
        
        def get_api_key():
            webbrowser.open("https://newsapi.org/register")
        
        tk.Button(button_frame, text="Get Free API Key",
                 command=get_api_key, bg=self.colors['accent'],
                 fg=self.colors['text_primary'], font=('Helvetica', 10),
                 relief='flat', padx=15, pady=5).pack(side=tk.LEFT)
        
        tk.Button(button_frame, text="Save & Continue",
                 command=save_and_close, bg=self.colors['success'],
                 fg=self.colors['text_primary'], font=('Helvetica', 10, 'bold'),
                 relief='flat', padx=15, pady=5).pack(side=tk.RIGHT)
    
    def save_api_key(self):
        """Save API key to .env file"""
        try:
            api_key = self.api_key_var.get().strip()
            if api_key:
                # Save to .env file
                with open('.env', 'w') as f:
                    f.write(f"NEWS_API_KEY={api_key}\n")
                
                self.api_key = api_key
                messagebox.showinfo("Success", "API key saved successfully!")
            else:
                messagebox.showerror("Error", "Please enter a valid API key")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save API key: {str(e)}")
    
    def open_newsapi_website(self):
        """Open NewsAPI website"""
        webbrowser.open("https://newsapi.org/register")

def main():
    """Main function to run the application"""
    # Check for required dependencies
    missing_deps = []
    
    try:
        import requests
    except ImportError:
        missing_deps.append("requests")
    
    try:
        import pandas
    except ImportError:
        missing_deps.append("pandas")
    
    if missing_deps:
        print("Missing required dependencies:")
        for dep in missing_deps:
            print(f"  - {dep}")
        print("\nInstall with: pip install", " ".join(missing_deps))
        return
    
    # Create and run the GUI
    root = tk.Tk()
    app = ModernNewsGUI(root)
    
    # Initial load
    if app.api_key:
        root.after(1000, app.refresh_news)  # Auto-load news after 1 second
    
    root.mainloop()

if __name__ == "__main__":
    main()