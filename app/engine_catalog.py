"""Auditable 156-engine capability catalogue for QUANT NEXUS.

A catalogue entry is not proof of a production-ready capability. Statuses
reflect tested runtime paths; approximations, missing feeds, untrained models
and deployment gaps remain explicit.
"""
from __future__ import annotations

ENGINE_CATALOG = [
  {
    "id": "E001",
    "name": "Market Data Ingestion",
    "name_ar": "محرك Market Data Ingestion",
    "group": "Market Intelligence",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E002",
    "name": "Order Book",
    "name_ar": "محرك Order Book",
    "group": "Market Intelligence",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E003",
    "name": "Liquidity",
    "name_ar": "محرك Liquidity",
    "group": "Market Intelligence",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E004",
    "name": "Volatility",
    "name_ar": "محرك Volatility",
    "group": "Market Intelligence",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E005",
    "name": "Data Normalization",
    "name_ar": "محرك Data Normalization",
    "group": "Market Intelligence",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E006",
    "name": "Data Quality",
    "name_ar": "محرك Data Quality",
    "group": "Market Intelligence",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E007",
    "name": "News and Events",
    "name_ar": "محرك News and Events",
    "group": "Market Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E008",
    "name": "Cross-Market Correlation",
    "name_ar": "محرك Cross-Market Correlation",
    "group": "Market Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E009",
    "name": "Trend",
    "name_ar": "محرك Trend",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E010",
    "name": "Market Structure",
    "name_ar": "محرك Market Structure",
    "group": "Technical Analysis",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E011",
    "name": "Support and Resistance",
    "name_ar": "محرك Support and Resistance",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "دعم ومقاومة من قمم وقيعان النطاق المتحرك"
    ],
    "gaps": [
      "النطاقات تقريبية وتتطلب تحققاً من بنية السوق والسيولة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E012",
    "name": "Supply and Demand",
    "name_ar": "محرك Supply and Demand",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "مناطق عرض وطلب تقريبية من نطاقات الدعم والمقاومة"
    ],
    "gaps": [
      "ليست دفتر أوامر مؤسسياً ولا تثبت وجود أوامر معلقة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E013",
    "name": "Smart Money Concepts",
    "name_ar": "محرك Smart Money Concepts",
    "group": "Technical Analysis",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E014",
    "name": "Order Block",
    "name_ar": "محرك Order Block",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "مرشح Order Block من آخر شمعة عكسية قبل كسر نطاقها"
    ],
    "gaps": [
      "تعريف تقريبي ولا يثبت تمركز جهة مؤسسية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E015",
    "name": "Fair Value Gap",
    "name_ar": "محرك Fair Value Gap",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "كشف فجوة ثلاث شمعات غير متداخلة"
    ],
    "gaps": [
      "مرشح هندسي لا يثبت استمرار الفجوة أو أهميتها"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E016",
    "name": "Breakout",
    "name_ar": "محرك Breakout",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "تأكيد اختراق بإغلاق شمعة مكتملة خارج نطاق 20 شمعة"
    ],
    "gaps": [
      "يتطلب تأكيد الحجم والسياق قبل اعتماد إشارة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E017",
    "name": "Reversal",
    "name_ar": "محرك Reversal",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "مرشحات انعكاس وانحراف RSI بين نوافذ سعرية"
    ],
    "gaps": [
      "النقاط المحورية والانحراف غير مؤكدين حتى اكتمال السياق"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E018",
    "name": "Momentum",
    "name_ar": "محرك Momentum",
    "group": "Technical Analysis",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E019",
    "name": "Candlestick Patterns",
    "name_ar": "محرك Candlestick Patterns",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "تصنيف هندسي لشموع Doji وHammer وEngulfing"
    ],
    "gaps": [
      "النماذج لا تعمل منفردة ولا تتضمن كل نماذج الشموع"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E020",
    "name": "Fibonacci",
    "name_ar": "محرك Fibonacci",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "مستويات ارتداد فيبوناتشي من نطاق 100 شمعة"
    ],
    "gaps": [
      "اختيار القمة والقاع تقريبي وقابل للتغير"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E021",
    "name": "VWAP",
    "name_ar": "محرك VWAP",
    "group": "Technical Analysis",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E022",
    "name": "Volume Profile",
    "name_ar": "محرك Volume Profile",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "توزيع حجم تقريبي حسب منتصف النطاق السعري"
    ],
    "gaps": [
      "ليس Volume-at-Price مبنياً على كل صفقة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E023",
    "name": "Divergence",
    "name_ar": "محرك Divergence",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "مرشحات انحراف RSI صاعد وهابط"
    ],
    "gaps": [
      "تحتاج تثبيت القمم والقيعان لتجنب الإشارات المبكرة الكاذبة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E024",
    "name": "Pattern Recognition",
    "name_ar": "محرك Pattern Recognition",
    "group": "Technical Analysis",
    "status": "partial",
    "capabilities": [
      "التعرف على أشكال شموع أساسية"
    ],
    "gaps": [
      "التعرف على النماذج المركبة والأنماط الإحصائية غير مكتمل"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E025",
    "name": "Multi-Timeframe Analysis",
    "name_ar": "محرك Multi-Timeframe Analysis",
    "group": "Multi-Timeframe",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E026",
    "name": "Higher Timeframe Analysis",
    "name_ar": "محرك Higher Timeframe Analysis",
    "group": "Multi-Timeframe",
    "status": "partial",
    "capabilities": [
      "قراءة اتجاه إطار 4 ساعات من لقطة مكتملة"
    ],
    "gaps": [
      "تعتمد على توفر مزود الإطار الزمني"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E027",
    "name": "Lower Timeframe Analysis",
    "name_ar": "محرك Lower Timeframe Analysis",
    "group": "Multi-Timeframe",
    "status": "partial",
    "capabilities": [
      "قراءة اتجاه إطار 5 أو 15 دقيقة"
    ],
    "gaps": [
      "تحتاج مزود إطار قصير مكتمل"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E028",
    "name": "Timeframe Synchronization",
    "name_ar": "محرك Timeframe Synchronization",
    "group": "Multi-Timeframe",
    "status": "partial",
    "capabilities": [
      "قياس توافق الاتجاهات بين الأطر الزمنية المتاحة"
    ],
    "gaps": [
      "لا يستبدل تحليل الاعتماد الزمني أو اختبار التأخر"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E029",
    "name": "Market Phase",
    "name_ar": "محرك Market Phase",
    "group": "Multi-Timeframe",
    "status": "partial",
    "capabilities": [
      "تصنيف مرحلة السوق من الانضغاط والامتصاص والاختراق"
    ],
    "gaps": [
      "التجميع والتوزيع استدلالات تقريبية لا حقائق مؤكدة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E030",
    "name": "Trading Sessions",
    "name_ar": "محرك Trading Sessions",
    "group": "Multi-Timeframe",
    "status": "partial",
    "capabilities": [
      "تصنيف جلسات آسيا ولندن ونيويورك وفق UTC"
    ],
    "gaps": [
      "النوافذ مبسطة ولا تشمل العطلات أو التوقيت الصيفي المحلي"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E031",
    "name": "Market Timing",
    "name_ar": "محرك Market Timing",
    "group": "Multi-Timeframe",
    "status": "partial",
    "capabilities": [
      "تحديد جلسة النشاط من وقت UTC"
    ],
    "gaps": [
      "لا يوفر توقيتاً تنبؤياً أو نموذج موسمية مدرباً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E032",
    "name": "Trend Exhaustion",
    "name_ar": "محرك Trend Exhaustion",
    "group": "Multi-Timeframe",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E033",
    "name": "Opportunity Hunter",
    "name_ar": "محرك Opportunity Hunter",
    "group": "Opportunity Hunter",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E034",
    "name": "Early Breakout Detector",
    "name_ar": "محرك Early Breakout Detector",
    "group": "Opportunity Hunter",
    "status": "partial",
    "capabilities": [
      "اكتشاف مرشح اختراق مبكر قرب حافة نطاق منضغط"
    ],
    "gaps": [
      "لا يضمن حدوث الاختراق وقد يفشل دون تأكيد لاحق"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E035",
    "name": "Accumulation Detector",
    "name_ar": "محرك Accumulation Detector",
    "group": "Opportunity Hunter",
    "status": "partial",
    "capabilities": [
      "تقييم ضغط الحجم وموقع الإغلاق داخل النطاق"
    ],
    "gaps": [
      "لا يحدد هوية المشتري أو نية المشاركين"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E036",
    "name": "Liquidity Sweep Hunter",
    "name_ar": "محرك Liquidity Sweep Hunter",
    "group": "Opportunity Hunter",
    "status": "partial",
    "capabilities": [
      "كشف سحب سيولة من قمم وقيعان سابقة ثم الإغلاق داخل النطاق"
    ],
    "gaps": [
      "إشارة OHLCV تقريبية وليست دليلاً على stop hunts مؤسسية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E037",
    "name": "Momentum Explosion Detector",
    "name_ar": "محرك Momentum Explosion Detector",
    "group": "Opportunity Hunter",
    "status": "partial",
    "capabilities": [
      "كشف توسع جسم الشمعة مقارنة بـ ATR مع شذوذ الحجم"
    ],
    "gaps": [
      "يعتمد على الشموع المكتملة والحدود الإحصائية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E038",
    "name": "Whale Activity Detector",
    "name_ar": "محرك Whale Activity Detector",
    "group": "Opportunity Hunter",
    "status": "partial",
    "capabilities": [
      "كشف صفقات كبيرة شاذة مقارنة بوسيط أحجام الصفقات"
    ],
    "gaps": [
      "لا يحدد المحافظ أو هوية الحيتان"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E039",
    "name": "Volume Anomaly Detector",
    "name_ar": "محرك Volume Anomaly Detector",
    "group": "Opportunity Hunter",
    "status": "partial",
    "capabilities": [
      "كشف حجم تداول غير طبيعي عبر z-score"
    ],
    "gaps": [
      "يحتاج حجم موثوق وفترات مكتملة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E040",
    "name": "Squeeze Detector",
    "name_ar": "محرك Squeeze Detector",
    "group": "Opportunity Hunter",
    "status": "partial",
    "capabilities": [
      "قياس انضغاط متوسط المدى السعري"
    ],
    "gaps": [
      "ليس نموذج Bollinger-Keltner squeeze متكاملاً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E041",
    "name": "Futures Opportunity Hunter",
    "name_ar": "محرك Futures Opportunity Hunter",
    "group": "Opportunity Hunter",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E042",
    "name": "Spot Opportunity Hunter",
    "name_ar": "محرك Spot Opportunity Hunter",
    "group": "Opportunity Hunter",
    "status": "partial",
    "capabilities": [
      "تقييم فرصة Spot مع مراعاة اتجاه الشراء"
    ],
    "gaps": [
      "مرشح مراقبة وليس أمراً أو توقع نجاح معايراً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E043",
    "name": "Cross-Exchange Arbitrage",
    "name_ar": "محرك Cross-Exchange Arbitrage",
    "group": "Opportunity Hunter",
    "status": "partial",
    "capabilities": [
      "مقارنة أسعار منصات متزامنة بعد رسوم وانزلاق مدخلين"
    ],
    "gaps": [
      "لا يحسب مخاطر التحويل والكمون والتنفيذ والرصيد المتاح"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E044",
    "name": "AI Market Analyst",
    "name_ar": "محرك AI Market Analyst",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E045",
    "name": "Machine Learning",
    "name_ar": "محرك Machine Learning",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E046",
    "name": "Deep Learning",
    "name_ar": "محرك Deep Learning",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E047",
    "name": "LSTM Forecast",
    "name_ar": "محرك LSTM Forecast",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E048",
    "name": "Transformer Forecast",
    "name_ar": "محرك Transformer Forecast",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E049",
    "name": "Reinforcement Learning",
    "name_ar": "محرك Reinforcement Learning",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E050",
    "name": "XGBoost Classifier",
    "name_ar": "محرك XGBoost Classifier",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E051",
    "name": "Random Forest Classifier",
    "name_ar": "محرك Random Forest Classifier",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E052",
    "name": "Anomaly Detection AI",
    "name_ar": "محرك Anomaly Detection AI",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E053",
    "name": "Clustering",
    "name_ar": "محرك Clustering",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E054",
    "name": "Market Regime Detection",
    "name_ar": "محرك Market Regime Detection",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E055",
    "name": "Predictive Analytics",
    "name_ar": "محرك Predictive Analytics",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E056",
    "name": "Probability Engine",
    "name_ar": "محرك Probability Engine",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E057",
    "name": "Ensemble AI",
    "name_ar": "محرك Ensemble AI",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E058",
    "name": "Adaptive Learning",
    "name_ar": "محرك Adaptive Learning",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E059",
    "name": "Explainable AI",
    "name_ar": "محرك Explainable AI",
    "group": "AI Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E060",
    "name": "Funding Rate",
    "name_ar": "محرك Funding Rate",
    "group": "Derivatives Intelligence",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E061",
    "name": "Open Interest",
    "name_ar": "محرك Open Interest",
    "group": "Derivatives Intelligence",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E062",
    "name": "Long Short Ratio",
    "name_ar": "محرك Long Short Ratio",
    "group": "Derivatives Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E063",
    "name": "Liquidation Heatmap",
    "name_ar": "محرك Liquidation Heatmap",
    "group": "Derivatives Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E064",
    "name": "Liquidation Tracker",
    "name_ar": "محرك Liquidation Tracker",
    "group": "Derivatives Intelligence",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E065",
    "name": "Basis Analysis",
    "name_ar": "محرك Basis Analysis",
    "group": "Derivatives Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E066",
    "name": "Futures Positioning",
    "name_ar": "محرك Futures Positioning",
    "group": "Derivatives Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E067",
    "name": "Leverage Risk Detector",
    "name_ar": "محرك Leverage Risk Detector",
    "group": "Derivatives Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E068",
    "name": "Derivatives Divergence",
    "name_ar": "محرك Derivatives Divergence",
    "group": "Derivatives Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E069",
    "name": "Options Analytics",
    "name_ar": "محرك Options Analytics",
    "group": "Derivatives Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E070",
    "name": "Implied Volatility",
    "name_ar": "محرك Implied Volatility",
    "group": "Derivatives Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E071",
    "name": "Gamma Exposure",
    "name_ar": "محرك Gamma Exposure",
    "group": "Derivatives Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E072",
    "name": "Opportunity Scoring",
    "name_ar": "محرك Opportunity Scoring",
    "group": "Opportunity Scoring",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E073",
    "name": "Confidence Assessment",
    "name_ar": "محرك Confidence Assessment",
    "group": "Opportunity Scoring",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E074",
    "name": "Risk Reward",
    "name_ar": "محرك Risk Reward",
    "group": "Opportunity Scoring",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E075",
    "name": "Entry Precision",
    "name_ar": "محرك Entry Precision",
    "group": "Opportunity Scoring",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E076",
    "name": "Stop Loss",
    "name_ar": "محرك Stop Loss",
    "group": "Opportunity Scoring",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E077",
    "name": "Take Profit",
    "name_ar": "محرك Take Profit",
    "group": "Opportunity Scoring",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E078",
    "name": "Trade Quality",
    "name_ar": "محرك Trade Quality",
    "group": "Opportunity Scoring",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E079",
    "name": "Signal Confirmation",
    "name_ar": "محرك Signal Confirmation",
    "group": "Opportunity Scoring",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E080",
    "name": "False Breakout Filter",
    "name_ar": "محرك False Breakout Filter",
    "group": "Opportunity Scoring",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E081",
    "name": "Signal Conflict Resolver",
    "name_ar": "محرك Signal Conflict Resolver",
    "group": "Opportunity Scoring",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E082",
    "name": "Opportunity Ranking",
    "name_ar": "محرك Opportunity Ranking",
    "group": "Opportunity Scoring",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E083",
    "name": "Signal Expiration",
    "name_ar": "محرك Signal Expiration",
    "group": "Opportunity Scoring",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E084",
    "name": "Expected Value",
    "name_ar": "محرك Expected Value",
    "group": "Opportunity Scoring",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E085",
    "name": "Entry Readiness",
    "name_ar": "محرك Entry Readiness",
    "group": "Opportunity Scoring",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E086",
    "name": "Position Sizing",
    "name_ar": "محرك Position Sizing",
    "group": "Risk Management",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E087",
    "name": "Dynamic Risk",
    "name_ar": "محرك Dynamic Risk",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E088",
    "name": "Portfolio Risk",
    "name_ar": "محرك Portfolio Risk",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E089",
    "name": "Maximum Drawdown",
    "name_ar": "محرك Maximum Drawdown",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E090",
    "name": "Correlation Risk",
    "name_ar": "محرك Correlation Risk",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E091",
    "name": "Exposure Management",
    "name_ar": "محرك Exposure Management",
    "group": "Risk Management",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E092",
    "name": "Liquidation Protection",
    "name_ar": "محرك Liquidation Protection",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E093",
    "name": "Slippage Estimation",
    "name_ar": "محرك Slippage Estimation",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E094",
    "name": "Fee Calculator",
    "name_ar": "محرك Fee Calculator",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E095",
    "name": "Volatility Stop",
    "name_ar": "محرك Volatility Stop",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E096",
    "name": "Breakeven",
    "name_ar": "محرك Breakeven",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E097",
    "name": "Trailing Stop",
    "name_ar": "محرك Trailing Stop",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E098",
    "name": "Daily Loss Limit",
    "name_ar": "محرك Daily Loss Limit",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E099",
    "name": "Circuit Breaker",
    "name_ar": "محرك Circuit Breaker",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E100",
    "name": "Risk Approval",
    "name_ar": "محرك Risk Approval",
    "group": "Risk Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E101",
    "name": "Backtesting",
    "name_ar": "محرك Backtesting",
    "group": "Backtesting & Learning",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E102",
    "name": "Walk Forward Validation",
    "name_ar": "محرك Walk Forward Validation",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E103",
    "name": "Paper Trading",
    "name_ar": "محرك Paper Trading",
    "group": "Backtesting & Learning",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E104",
    "name": "Monte Carlo Simulation",
    "name_ar": "محرك Monte Carlo Simulation",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E105",
    "name": "Strategy Optimizer",
    "name_ar": "محرك Strategy Optimizer",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E106",
    "name": "Parameter Optimization",
    "name_ar": "محرك Parameter Optimization",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E107",
    "name": "Overfitting Detection",
    "name_ar": "محرك Overfitting Detection",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E108",
    "name": "Out-of-Sample Validation",
    "name_ar": "محرك Out-of-Sample Validation",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E109",
    "name": "Performance Attribution",
    "name_ar": "محرك Performance Attribution",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E110",
    "name": "Win Rate Analytics",
    "name_ar": "محرك Win Rate Analytics",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E111",
    "name": "Profit Factor",
    "name_ar": "محرك Profit Factor",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E112",
    "name": "Trade Expectancy",
    "name_ar": "محرك Trade Expectancy",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E113",
    "name": "Strategy Comparison",
    "name_ar": "محرك Strategy Comparison",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E114",
    "name": "Model Drift Detection",
    "name_ar": "محرك Model Drift Detection",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E115",
    "name": "Continuous Learning",
    "name_ar": "محرك Continuous Learning",
    "group": "Backtesting & Learning",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E116",
    "name": "Trade Lifecycle",
    "name_ar": "محرك Trade Lifecycle",
    "group": "Trade Management",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E117",
    "name": "Live Position Monitor",
    "name_ar": "محرك Live Position Monitor",
    "group": "Trade Management",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E118",
    "name": "Entry Confirmation Monitor",
    "name_ar": "محرك Entry Confirmation Monitor",
    "group": "Trade Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E119",
    "name": "Target Tracker",
    "name_ar": "محرك Target Tracker",
    "group": "Trade Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E120",
    "name": "Stop Loss Monitor",
    "name_ar": "محرك Stop Loss Monitor",
    "group": "Trade Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E121",
    "name": "Smart Exit",
    "name_ar": "محرك Smart Exit",
    "group": "Trade Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E122",
    "name": "Partial Profit Taking",
    "name_ar": "محرك Partial Profit Taking",
    "group": "Trade Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E123",
    "name": "Trade Recovery",
    "name_ar": "محرك Trade Recovery",
    "group": "Trade Management",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E124",
    "name": "Trade Journal",
    "name_ar": "محرك Trade Journal",
    "group": "Trade Management",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E125",
    "name": "Opportunity Monitoring Room",
    "name_ar": "محرك Opportunity Monitoring Room",
    "group": "Trade Management",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E126",
    "name": "Central Quant Brain",
    "name_ar": "محرك Central Quant Brain",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "partial_existing_capability"
  },
  {
    "id": "E127",
    "name": "Market Analyst Agent",
    "name_ar": "محرك Market Analyst Agent",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E128",
    "name": "Liquidity Agent",
    "name_ar": "محرك Liquidity Agent",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E129",
    "name": "Smart Money Agent",
    "name_ar": "محرك Smart Money Agent",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E130",
    "name": "Derivatives Agent",
    "name_ar": "محرك Derivatives Agent",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E131",
    "name": "Technical Analysis Agent",
    "name_ar": "محرك Technical Analysis Agent",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E132",
    "name": "AI Prediction Agent",
    "name_ar": "محرك AI Prediction Agent",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E133",
    "name": "Risk Officer Agent",
    "name_ar": "محرك Risk Officer Agent",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E134",
    "name": "Strategy Manager Agent",
    "name_ar": "محرك Strategy Manager Agent",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E135",
    "name": "Decision Fusion",
    "name_ar": "محرك Decision Fusion",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E136",
    "name": "Agent Disagreement",
    "name_ar": "محرك Agent Disagreement",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E137",
    "name": "Consensus Engine",
    "name_ar": "محرك Consensus Engine",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E138",
    "name": "Knowledge Memory",
    "name_ar": "محرك Knowledge Memory",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E139",
    "name": "Adaptive Strategy Router",
    "name_ar": "محرك Adaptive Strategy Router",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E140",
    "name": "Autonomous Research",
    "name_ar": "محرك Autonomous Research",
    "group": "Multi-Agent Intelligence",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E141",
    "name": "Scheduler",
    "name_ar": "محرك Scheduler",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E142",
    "name": "Event Bus",
    "name_ar": "محرك Event Bus",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E143",
    "name": "Cache",
    "name_ar": "محرك Cache",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E144",
    "name": "Database",
    "name_ar": "محرك Database",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E145",
    "name": "WebSocket Manager",
    "name_ar": "محرك WebSocket Manager",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E146",
    "name": "API Gateway",
    "name_ar": "محرك API Gateway",
    "group": "Infrastructure",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E147",
    "name": "Health Monitor",
    "name_ar": "محرك Health Monitor",
    "group": "Infrastructure",
    "status": "implemented",
    "capabilities": [
      "وجود مسار وظيفي مرتبط في النسخة الحالية"
    ],
    "gaps": [],
    "evidence": "verified_existing_capability"
  },
  {
    "id": "E148",
    "name": "Error Recovery",
    "name_ar": "محرك Error Recovery",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E149",
    "name": "Duplicate Signal Filter",
    "name_ar": "محرك Duplicate Signal Filter",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E150",
    "name": "Notification Engine",
    "name_ar": "محرك Notification Engine",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E151",
    "name": "Audit Log",
    "name_ar": "محرك Audit Log",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E152",
    "name": "Model Registry",
    "name_ar": "محرك Model Registry",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E153",
    "name": "Data Replay",
    "name_ar": "محرك Data Replay",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E154",
    "name": "Security Engine",
    "name_ar": "محرك Security Engine",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E155",
    "name": "Resource Manager",
    "name_ar": "محرك Resource Manager",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  },
  {
    "id": "E156",
    "name": "Watchdog",
    "name_ar": "محرك Watchdog",
    "group": "Infrastructure",
    "status": "planned",
    "capabilities": [],
    "gaps": [
      "يحتاج تنفيذ مستقل واختبارات قبول قبل اعتباره جاهزاً"
    ],
    "evidence": "not_yet_implemented"
  }
]

def engine_catalog() -> dict:
    engines = [dict(item, capabilities=list(item.get("capabilities", [])),
                    gaps=list(item.get("gaps", []))) for item in ENGINE_CATALOG]
    statuses = ("implemented", "partial", "planned")
    counts = {status: sum(1 for item in engines if item["status"] == status)
              for status in statuses}
    groups = sorted({item["group"] for item in engines})
    group_counts = {group: sum(1 for item in engines if item["group"] == group) for group in groups}
    return {"name":"QUANT NEXUS","catalog_version":"1.1.0","total":len(engines),
            "counts":counts,"group_counts":group_counts,"engines":engines,
            "priority":"early_opportunity_detection","trading_mode":"simulation",
            "live_trading_enabled":False,"execution_capability":"paper_only",
            "disclaimer":"Partial entries use explicit proxies and still have listed gaps. Planned entries cannot generate market signals."}
