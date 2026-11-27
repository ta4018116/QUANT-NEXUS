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
    "status": "implemented",
    "capabilities": [
      "توحيد حقول OHLCV والتحقق من القيم المالية والطوابع الزمنية",
      "ترتيب الشموع وإزالة التكرارات وإرجاع البيانات المعيارية"
    ],
    "gaps": [
    ],
    "limitations": [
      "لا يستنتج الشموع المفقودة؛ يعرض الصفوف المرفوضة والتكرارات بدلاً من اختلاق بيانات"
    ],
    "evidence": "dedicated_normalization_acceptance_tests"
  },
  {
    "id": "E006",
    "name": "Data Quality",
    "name_ar": "محرك Data Quality",
    "group": "Market Intelligence",
    "status": "implemented",
    "capabilities": [
      "فحص الشموع الخام للقيم المالية غير الصالحة والحدود المنطقية لـ OHLCV",
      "كشف الطوابع الزمنية المفقودة أو المكررة أو غير المرتبة"
    ],
    "gaps": [
    ],
    "limitations": [
      "يكشف الترتيب والتكرار ولا يحكم على فجوات جلسات السوق من دون تقويم المصدر"
    ],
    "evidence": "dedicated_raw_data_quality_acceptance_tests"
  },
  {
    "id": "E007",
    "name": "News and Events",
    "name_ar": "محرك News and Events",
    "group": "Market Intelligence",
    "status": "implemented",
    "capabilities": [
      "اكتشاف عناوين من RSS وGDELT وتطبيع المصدر والتوقيت والرابط",
      "فرز كلمات مفتاحية أولي مع حفظ الإسناد لمصدر الخبر"
    ],
    "gaps": [],
    "limitations": [
      "تصنيف الكلمات للفرز فقط ولا يتحقق من صحة الخبر أو أثره السببي على السعر"
    ],
    "evidence": "public_news_feed_and_keyword_triage_acceptance_tests"
  },
  {
    "id": "E008",
    "name": "Cross-Market Correlation",
    "name_ar": "محرك Cross-Market Correlation",
    "group": "Market Intelligence",
    "status": "implemented",
    "capabilities": [
      "حساب ارتباط Pearson لعوائد الأصول المتزامنة زمنياً",
      "اشتراط تداخل كافٍ واستبعاد الأطر غير المتزامنة"
    ],
    "gaps": [],
    "limitations": [
      "يفحص سلة صغيرة من الأصول السائلة ولا يثبت علاقة سببية أو تنبؤية"
    ],
    "evidence": "aligned_peer_feed_and_correlation_acceptance_tests"
  },
  {
    "id": "E009",
    "name": "Trend",
    "name_ar": "محرك Trend",
    "group": "Technical Analysis",
    "status": "implemented",
    "capabilities": [
      "تصنيف اتجاه EMA20 وEMA50 مع ميل إغلاق 20 شمعة مكتملة"
    ],
    "gaps": [],
    "limitations": [
      "مرشح اتجاهي محدد؛ لا يمثل توقعاً أو احتمال ربح"
    ],
    "evidence": "dedicated_trend_acceptance_tests"
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
    "status": "implemented",
    "capabilities": [
      "نطاقات دعم ومقاومة من ترتيب القيعان والقمم ضمن آخر 50 شمعة مكتملة"
    ],
    "gaps": [],
    "limitations": [
      "مستويات نطاقية حسابية وليست إثباتاً لوجود أوامر معلقة أو سيولة مؤسسية"
    ],
    "evidence": "dedicated_rolling_extrema_support_resistance_acceptance_tests"
  },
  {
    "id": "E012",
    "name": "Supply and Demand",
    "name_ar": "محرك Supply and Demand",
    "group": "Technical Analysis",
    "status": "implemented",
    "capabilities": [
      "تصنيف نطاق الدعم المحسوب طلباً ونطاق المقاومة المحسوب عرضاً مع فحص قرب السعر"
    ],
    "gaps": [],
    "limitations": [
      "مناطق مشتقة من نطاقات القمم والقيعان، ولا تثبت وجود أوامر معلقة"
    ],
    "evidence": "dedicated_supply_demand_zone_acceptance_tests"
  },
  {
    "id": "E013",
    "name": "Smart Money Concepts",
    "name_ar": "محرك Smart Money Concepts",
    "group": "Technical Analysis",
    "status": "implemented",
    "capabilities": [
      "تجميع نتائج بنية السوق وسحب السيولة ومرشح Order Block وFair Value Gap"
    ],
    "gaps": [],
    "limitations": [
      "تجميع شفاف لمؤشرات حركة السعر؛ لا يثبت تدفقات أوامر مؤسسية"
    ],
    "evidence": "dedicated_smc_component_acceptance_tests"
  },
  {
    "id": "E014",
    "name": "Order Block",
    "name_ar": "محرك Order Block",
    "group": "Technical Analysis",
    "status": "implemented",
    "capabilities": [
      "كشف آخر شمعة عكسية قبل إغلاق الشمعة التالية خارج نطاقها الكامل"
    ],
    "gaps": [],
    "limitations": [
      "قاعدة سعرية محددة لا تثبت تمركز جهة مؤسسية أو استمرار أثر المنطقة"
    ],
    "evidence": "dedicated_order_block_breakout_acceptance_tests"
  },
  {
    "id": "E015",
    "name": "Fair Value Gap",
    "name_ar": "محرك Fair Value Gap",
    "group": "Technical Analysis",
    "status": "implemented",
    "capabilities": [
      "كشف الفجوات الصاعدة والهابطة بين الشمعة الأولى والثالثة من كل نافذة ثلاثية"
    ],
    "gaps": [],
    "limitations": [
      "هندسة شموع مكتملة؛ لا تقيس احتمال بقاء الفجوة أو أهميتها المستقبلية"
    ],
    "evidence": "dedicated_three_candle_fvg_acceptance_tests"
  },
  {
    "id": "E016",
    "name": "Breakout",
    "name_ar": "محرك Breakout",
    "group": "Technical Analysis",
    "status": "implemented",
    "capabilities": [
      "رصد إغلاق شمعة مكتملة خارج أعلى أو أدنى نطاق 20 شمعة سابقة مع نسبة حجم مرجعية"
    ],
    "gaps": [],
    "limitations": [
      "إشارة نطاق وحجم محددة؛ لا تثبت استمرار الاختراق أو ربحية الصفقة"
    ],
    "evidence": "dedicated_completed_candle_breakout_acceptance_tests"
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
    "status": "implemented",
    "capabilities": [
      "مستويات 23.6% و38.2% و50% و61.8% و78.6% من نطاق أعلى وأدنى آخر 100 شمعة مكتملة"
    ],
    "gaps": [],
    "limitations": [
      "مرجع ارتداد حسابي يتغير مع نافذة 100 شمعة ولا يحدد وحده نقطة انعكاس"
    ],
    "evidence": "dedicated_fibonacci_window_level_acceptance_tests"
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
      "اتفاق اتجاهي لأطر متعددة من شموع مكتملة وحديثة"
    ],
    "gaps": [],
    "limitations": ["توافق الاتجاه لا يثبت علاقة سببية ولا يتضمن اختبار تأخر زمني"],
    "evidence": "fresh_completed_multi_timeframe_acceptance_tests"
  },
  {
    "id": "E026",
    "name": "Higher Timeframe Analysis",
    "name_ar": "محرك Higher Timeframe Analysis",
    "group": "Multi-Timeframe",
    "status": "implemented",
    "capabilities": [
      "قراءة اتجاه إطار 4 ساعات من لقطة مكتملة"
    ],
    "gaps": [],
    "limitations": ["لقطة 4 ساعات اتجاهية للقراءة فقط ومقيدة بعمر الشمعة المكتملة"],
    "evidence": "fresh_completed_higher_timeframe_acceptance_tests"
  },
  {
    "id": "E027",
    "name": "Lower Timeframe Analysis",
    "name_ar": "محرك Lower Timeframe Analysis",
    "group": "Multi-Timeframe",
    "status": "implemented",
    "capabilities": [
      "قراءة اتجاه إطار 5 أو 15 دقيقة"
    ],
    "gaps": [],
    "limitations": ["يستخدم إطار 5 أو 15 دقيقة عند وجود لقطة مكتملة وحديثة فقط"],
    "evidence": "fresh_completed_lower_timeframe_acceptance_tests"
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
    "status": "partial",
    "capabilities": [
      "كشف تباطؤ العائد القصير مع حالات RSI المتطرفة"
    ],
    "gaps": [
      "مرشح إنهاك لا يؤكد انعكاس الاتجاه"
    ],
    "evidence": "partial_engine_runtime_adapter"
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
    "status": "implemented",
    "capabilities": [
      "كشف حجم تداول غير طبيعي عبر z-score"
    ],
    "gaps": [],
    "limitations": ["z-score أحادي المصدر يقيس شذوذ الحجم ولا يحدد سببه أو هوية المتداول"],
    "evidence": "positive_volume_baseline_and_anomaly_acceptance_tests"
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
    "status": "partial",
    "capabilities": [
      "تركيب تحليلي حتمي لاتجاه السوق والانضغاط والحجم والتجميع"
    ],
    "gaps": [
      "محلل تفسيري قائم على قواعد وليس نموذجاً لغوياً توليدياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E045",
    "name": "Machine Learning",
    "name_ar": "محرك Machine Learning",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "انحدار لوجستي منظم بميزات OHLCV مع فصل زمني 80/20"
    ],
    "gaps": [
      "نموذج بحثي صغير لا يملك معايرة مستقلة أو تحققاً مستقبلياً كافياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E046",
    "name": "Deep Learning",
    "name_ar": "محرك Deep Learning",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "شبكة MLP ذات طبقتين مخفيتين لتصنيف اتجاه العائد مع اختبار زمني"
    ],
    "gaps": [
      "نموذج صغير يعاد تدريبه لكل طلب وليس نموذجاً عميقاً محفوظاً أو معايراً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E047",
    "name": "LSTM Forecast",
    "name_ar": "محرك LSTM Forecast",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "مستخرج تسلسلي LSTM ببوابات متكررة ثابتة مع رأس تصنيف لوجستي مدرّب زمنياً"
    ],
    "gaps": [
      "الأوزان المتكررة ثابتة وحتمية والرأس فقط يُدرّب لكل طلب؛ ليس نموذج LSTM كاملاً مدرّباً عبر BPTT أو نموذجاً محفوظاً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E048",
    "name": "Transformer Forecast",
    "name_ar": "محرك Transformer Forecast",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "مستخرج تسلسلي Transformer أحادي الرأس بترميز موضعي وإسقاطات Q/K/V ثابتة مع رأس تصنيف مدرّب"
    ],
    "gaps": [
      "إسقاطات الانتباه ثابتة والرأس فقط يُدرّب لكل طلب؛ ليس Transformer كاملاً مدرّباً طرفاً لطرف أو نموذجاً محفوظاً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E049",
    "name": "Reinforcement Learning",
    "name_ar": "محرك Reinforcement Learning",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "وكيل Q-learning جدولي على بيئة OHLCV تجريبية مع حجز زمني للاختبار"
    ],
    "gaps": [
      "حالة السوق والأفعال والرسوم مبسطة ولا تثبت أفضلية تداول قابلة للنشر"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E050",
    "name": "XGBoost Classifier",
    "name_ar": "محرك XGBoost Classifier",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "مصنف أشجار تعزيز تدرجي بخسارة لوجستية ومكاسب من الرتبة الثانية على OHLCV مع اختبار زمني"
    ],
    "gaps": [
      "تنفيذ بحثي مبسط مستوحى من XGBoost وليس مكتبة XGBoost الأصلية، دون GPU أو أدوات معايرة ونشر نموذج"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E051",
    "name": "Random Forest Classifier",
    "name_ar": "محرك Random Forest Classifier",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "غابة عشوائية نقية من 21 شجرة ضحلة مع عينة اختبار زمنية"
    ],
    "gaps": [
      "غابة بحثية محدودة العمق ولا تعتمد مكتبة ML إنتاجية أو معايرة احتمالات"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E052",
    "name": "Anomaly Detection AI",
    "name_ar": "محرك Anomaly Detection AI",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "كشف شذوذ z-score للعائد والحجم ومدى الشمعة"
    ],
    "gaps": [
      "النافذة قصيرة وحدود الشذوذ إرشادية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E053",
    "name": "Clustering",
    "name_ar": "محرك Clustering",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "تجميع K-means بثلاث مجموعات لميزات العائد والتقلب والحجم"
    ],
    "gaps": [
      "التجميع وصفي ويتأثر بالفترة والتهيئة ولا يتنبأ بالاتجاه"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E054",
    "name": "Market Regime Detection",
    "name_ar": "محرك Market Regime Detection",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "تصنيف النظام من EMA وATR والانضغاط"
    ],
    "gaps": [
      "قواعد تقريبية وليست نموذج Regime تعلمياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E055",
    "name": "Predictive Analytics",
    "name_ar": "محرك Predictive Analytics",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "توقع مرجعي من متوسط العوائد التاريخية والانحراف"
    ],
    "gaps": [
      "إسقاط خطي بسيط وليس توقعاً معايراً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E056",
    "name": "Probability Engine",
    "name_ar": "محرك Probability Engine",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "قياس التكرار التاريخي للاتجاه الصاعد على أفق ثلاث شمعات"
    ],
    "gaps": [
      "معدل أساسي غير مشروط وليس احتمالاً خاصاً بالفرصة الحالية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E057",
    "name": "Ensemble AI",
    "name_ar": "محرك Ensemble AI",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "تجميع مخرجات الانحدار اللوجستي والغابة والاتجاه"
    ],
    "gaps": [
      "دمج بحثي غير موزون وغير معاير"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E058",
    "name": "Adaptive Learning",
    "name_ar": "محرك Adaptive Learning",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "إعادة تدريب بحثي زمني عند طلب التقييم على نافذة البيانات المقدمة"
    ],
    "gaps": [
      "لا يحفظ نموذجاً دائماً ولا يرقّي استراتيجية تلقائياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E059",
    "name": "Explainable AI",
    "name_ar": "محرك Explainable AI",
    "group": "AI Intelligence",
    "status": "partial",
    "capabilities": [
      "تفسير مساهمات ميزات الانحدار اللوجستي المعيارية"
    ],
    "gaps": [
      "المساهمات ارتباطية وليست تفسيراً سببياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
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
    "status": "partial",
    "capabilities": [
      "قراءة نسبة Long/Short عند توافرها ضمن بيانات المشتقات"
    ],
    "gaps": [
      "مزود النسبة غير مدمج في كل مسارات السوق"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E063",
    "name": "Liquidation Heatmap",
    "name_ar": "محرك Liquidation Heatmap",
    "group": "Derivatives Intelligence",
    "status": "partial",
    "capabilities": [
      "تجميع سجلات التصفية المنفذة حسب مستويات السعر"
    ],
    "gaps": [
      "لا يتنبأ بمناطق التصفية المستقبلية ولا توجد تغطية تاريخية موحدة لكل المنصات"
    ],
    "evidence": "partial_engine_runtime_adapter"
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
    "status": "partial",
    "capabilities": [
      "حساب أساس السعر بين Spot وFutures المتزامنين"
    ],
    "gaps": [
      "يتطلب علامات أسعار متزامنة من مزودين"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E066",
    "name": "Futures Positioning",
    "name_ar": "محرك Futures Positioning",
    "group": "Derivatives Intelligence",
    "status": "partial",
    "capabilities": [
      "قراءة التمويل والفائدة المفتوحة لتوصيف تمركز العقود"
    ],
    "gaps": [
      "محدود ببيانات Bybit المتاحة ولا يشمل كل المنصات"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E067",
    "name": "Leverage Risk Detector",
    "name_ar": "محرك Leverage Risk Detector",
    "group": "Derivatives Intelligence",
    "status": "partial",
    "capabilities": [
      "تقدير أولي لخطر الرافعة وسعر التصفية حسب صيانة الهامش"
    ],
    "gaps": [
      "تقريب معزول لا يطابق جداول التصفية الفعلية للمنصة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E068",
    "name": "Derivatives Divergence",
    "name_ar": "محرك Derivatives Divergence",
    "group": "Derivatives Intelligence",
    "status": "partial",
    "capabilities": [
      "مقارنة تغير السعر بتغير الفائدة المفتوحة"
    ],
    "gaps": [
      "يتطلب سلسلة OI تاريخية موثوقة ومقارنة زمنية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E069",
    "name": "Options Analytics",
    "name_ar": "محرك Options Analytics",
    "group": "Derivatives Intelligence",
    "status": "partial",
    "capabilities": [
      "تحليل سلسلة الخيارات وحساب Delta وGamma وVega عند توافر عقود وأسعار موثوقة"
    ],
    "gaps": [
      "لا يوجد مزود خيارات حي موصول حالياً؛ الحسابات تحتاج بيانات العقد وعلامة الأصل"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E070",
    "name": "Implied Volatility",
    "name_ar": "محرك Implied Volatility",
    "group": "Derivatives Intelligence",
    "status": "partial",
    "capabilities": [
      "استخراج IV من بيانات المزود أو تقديرها عددياً من سعر منتصف العرض والطلب"
    ],
    "gaps": [
      "Black-Scholes يفترض نموذجاً مبسطاً ولا يعكس ابتسامة التقلب أو القيود السوقية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E071",
    "name": "Gamma Exposure",
    "name_ar": "محرك Gamma Exposure",
    "group": "Derivatives Intelligence",
    "status": "partial",
    "capabilities": [
      "حساب التعرض الإجمالي لغاما من Gamma وOI ومضاعف العقد والسعر"
    ],
    "gaps": [
      "لا يمكن تقدير صافي تمركز صناع السوق من OI وحده دون إشارة تمركز موثوقة"
    ],
    "evidence": "partial_engine_runtime_adapter"
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
    "status": "partial",
    "capabilities": [
      "درجة توافق وتغطية أدلة المحركات"
    ],
    "gaps": [
      "ليست احتمال نجاح ولا معايرة إحصائية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E074",
    "name": "Risk Reward",
    "name_ar": "محرك Risk Reward",
    "group": "Opportunity Scoring",
    "status": "implemented",
    "capabilities": [
      "حساب مسافة المخاطرة والعائد ونسبة R:R من خطة ورقية مكتملة",
      "مقارنة النسبة بحد أدنى معلن من دون إصدار أمر"
    ],
    "gaps": [],
    "limitations": ["لا يخصم الرسوم والتمويل والانزلاق أو احتمال عدم التنفيذ"],
    "evidence": "dedicated_reward_risk_acceptance_tests"
  },
  {
    "id": "E075",
    "name": "Entry Precision",
    "name_ar": "محرك Entry Precision",
    "group": "Opportunity Scoring",
    "status": "partial",
    "capabilities": [
      "نطاق مراقبة للدخول قائم على ATR وVWAP والدعم والمقاومة"
    ],
    "gaps": [
      "لا ينتج أمراً محدداً أو ضمان تنفيذ"
    ],
    "evidence": "partial_engine_runtime_adapter"
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
    "status": "implemented",
    "capabilities": [
      "حساب أهداف مرجعية متعددة من نسبة العائد إلى المخاطرة"
    ],
    "gaps": [],
    "limitations": ["أهداف مرجعية حسابية فقط؛ لا تنشئ أوامر جني أرباح"],
    "evidence": "take_profit_reference_acceptance_tests"
  },
  {
    "id": "E078",
    "name": "Trade Quality",
    "name_ar": "محرك Trade Quality",
    "group": "Opportunity Scoring",
    "status": "partial",
    "capabilities": [
      "جودة الخطة من نسبة العائد للمخاطرة ودرجات الأدلة"
    ],
    "gaps": [
      "التصنيف إرشادي ويتأثر بمدخلات المستخدم"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E079",
    "name": "Signal Confirmation",
    "name_ar": "محرك Signal Confirmation",
    "group": "Opportunity Scoring",
    "status": "implemented",
    "capabilities": [
      "اشتراط تأكيد الشمعة المكتملة وموافقة جميع فحوص المخاطر قبل جاهزية المراقبة"
    ],
    "gaps": [],
    "limitations": ["يعتمد على نتائج التأكيد والمخاطر الموقعة من المحركات السابقة"],
    "evidence": "signal_confirmation_acceptance_tests"
  },
  {
    "id": "E080",
    "name": "False Breakout Filter",
    "name_ar": "محرك False Breakout Filter",
    "group": "Opportunity Scoring",
    "status": "partial",
    "capabilities": [
      "كشف عودة السعر داخل النطاق بعد اختراق الشمعة السابقة"
    ],
    "gaps": [
      "يحتاج شموع مكتملة وقد يتأخر تأكيد الفشل"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E081",
    "name": "Signal Conflict Resolver",
    "name_ar": "محرك Signal Conflict Resolver",
    "group": "Opportunity Scoring",
    "status": "implemented",
    "capabilities": [
      "حل تعارض اتجاهات وكلاء التحليل بالتصويت"
    ],
    "gaps": [],
    "limitations": ["تصويت شفاف غير موزون؛ الوكلاء قواعد مترابطة من اللقطة نفسها"],
    "evidence": "agent_conflict_acceptance_tests"
  },
  {
    "id": "E082",
    "name": "Opportunity Ranking",
    "name_ar": "محرك Opportunity Ranking",
    "group": "Opportunity Scoring",
    "status": "implemented",
    "capabilities": [
      "ترتيب فرص مزودة مسبقاً حسب درجاتها"
    ],
    "gaps": [],
    "limitations": ["يرتب المرشحين المزودين فقط؛ لا يمسح الكون ولا يعيد احتساب جودة مصادرهم"],
    "evidence": "opportunity_ranking_acceptance_tests"
  },
  {
    "id": "E083",
    "name": "Signal Expiration",
    "name_ar": "محرك Signal Expiration",
    "group": "Opportunity Scoring",
    "status": "partial",
    "capabilities": [
      "تحديد انتهاء صلاحية الإشارة من عمرها ووقت UTC"
    ],
    "gaps": [
      "يتطلب وقت إنشاء الإشارة والوقت الحالي من مصدر موثوق"
    ],
    "evidence": "partial_engine_runtime_adapter"
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
    "status": "implemented",
    "capabilities": [
      "جاهزية الدخول عبر اجتماع التأكيد وموافقة المخاطر"
    ],
    "gaps": [],
    "limitations": ["يتطلب نتائج تأكيد ومخاطر حديثة من المحركات السابقة"],
    "evidence": "entry_readiness_acceptance_tests"
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
    "status": "partial",
    "capabilities": [
      "تعديل المخاطرة وفق التقلب والتراجع"
    ],
    "gaps": [
      "قواعد ثابتة وليست معايرة حسب استراتيجية أو أصل"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E088",
    "name": "Portfolio Risk",
    "name_ar": "محرك Portfolio Risk",
    "group": "Risk Management",
    "status": "partial",
    "capabilities": [
      "حساب التعرض الاسمي للمراكز التجريبية مقابل حقوق الحساب"
    ],
    "gaps": [
      "لا يحسب كل مخاطر الارتباط أو الهامش"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E089",
    "name": "Maximum Drawdown",
    "name_ar": "محرك Maximum Drawdown",
    "group": "Risk Management",
    "status": "partial",
    "capabilities": [
      "حساب أقصى تراجع من تسلسل أرباح وخسائر المراكز المغلقة"
    ],
    "gaps": [
      "لا يشمل الربح والخسارة العائمين"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E090",
    "name": "Correlation Risk",
    "name_ar": "محرك Correlation Risk",
    "group": "Risk Management",
    "status": "partial",
    "capabilities": [
      "تصنيف أزواج ارتباط عالية من بيانات ارتباط مزودة"
    ],
    "gaps": [
      "يتطلب سلاسل عوائد متزامنة للمحفظة"
    ],
    "evidence": "partial_engine_runtime_adapter"
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
    "status": "partial",
    "capabilities": [
      "مقارنة الوقف بسعر تصفية تقريبي للرافعة"
    ],
    "gaps": [
      "يعتمد هامش صيانة مبسط ولا يضمن الحماية الفعلية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E093",
    "name": "Slippage Estimation",
    "name_ar": "محرك Slippage Estimation",
    "group": "Risk Management",
    "status": "partial",
    "capabilities": [
      "محاكاة عبور مستويات دفتر الأوامر لتقدير الانزلاق"
    ],
    "gaps": [
      "لا يحسب أولوية الطابور أو السيولة المخفية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E094",
    "name": "Fee Calculator",
    "name_ar": "محرك Fee Calculator",
    "group": "Risk Management",
    "status": "partial",
    "capabilities": [
      "حساب رسوم التداول من قيمة الصفقة ومعدل الرسوم"
    ],
    "gaps": [
      "يجب تزويده بمعدل الرسوم الصحيح لكل حساب ومنصة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E095",
    "name": "Volatility Stop",
    "name_ar": "محرك Volatility Stop",
    "group": "Risk Management",
    "status": "implemented",
    "capabilities": [
      "وقف مرجعي متكيف مع ATR"
    ],
    "gaps": [],
    "limitations": ["يعرض مرجع وقف ATR ولا يغيّر مراكز أو أوامر"],
    "evidence": "volatility_stop_acceptance_tests"
  },
  {
    "id": "E096",
    "name": "Breakeven",
    "name_ar": "محرك Breakeven",
    "group": "Risk Management",
    "status": "partial",
    "capabilities": [
      "حساب سعر التعادل بعد رسوم الدخول والخروج"
    ],
    "gaps": [
      "لا يشمل التمويل والانزلاق والضرائب"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E097",
    "name": "Trailing Stop",
    "name_ar": "محرك Trailing Stop",
    "group": "Risk Management",
    "status": "partial",
    "capabilities": [
      "حساب وقف متحرك مرجعي من أعلى/أدنى سعر وATR"
    ],
    "gaps": [
      "لا يحرك مراكز فعلية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E098",
    "name": "Daily Loss Limit",
    "name_ar": "محرك Daily Loss Limit",
    "group": "Risk Management",
    "status": "implemented",
    "capabilities": [
      "قياس خسارة اليوم مقابل حد خسارة محدد"
    ],
    "gaps": [],
    "limitations": ["يعتمد على PnL المحقق الممرر من سجل المحاكاة ولا يشمل الربح العائم"],
    "evidence": "paper_daily_loss_limit_acceptance_tests"
  },
  {
    "id": "E099",
    "name": "Circuit Breaker",
    "name_ar": "محرك Circuit Breaker",
    "group": "Risk Management",
    "status": "partial",
    "capabilities": [
      "قاطع منطقي يعتمد حد الخسارة وصحة الخدمات"
    ],
    "gaps": [
      "حالة مراقبة فقط ولا يوقف خدمات التنفيذ الخارجية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E100",
    "name": "Risk Approval",
    "name_ar": "محرك Risk Approval",
    "group": "Risk Management",
    "status": "implemented",
    "capabilities": [
      "بوابة موافقة تفشل عند أي فحص مخاطرة مفقود أو مرفوض"
    ],
    "gaps": [],
    "limitations": ["يجمع نتائج الفحوص؛ لا ينشئ أوامر أو يوقف منصة خارجية"],
    "evidence": "fail_closed_risk_approval_acceptance_tests"
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
    "status": "partial",
    "capabilities": [
      "تقسيم عوائد الاستراتيجية زمنياً إلى تدريب واختبار"
    ],
    "gaps": [
      "تقسيم واحد وليس Walk-Forward متكرر كامل"
    ],
    "evidence": "partial_engine_runtime_adapter"
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
    "status": "partial",
    "capabilities": [
      "محاكاة Monte Carlo بإعادة سحب عوائد تاريخية"
    ],
    "gaps": [
      "لا تمثل توقعاً لاحتمالات المستقبل"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E105",
    "name": "Strategy Optimizer",
    "name_ar": "محرك Strategy Optimizer",
    "group": "Backtesting & Learning",
    "status": "partial",
    "capabilities": [
      "ترتيب نتائج استراتيجيات اختبار مستقلة وفق العائد والتراجع وعدد الصفقات"
    ],
    "gaps": [
      "لا يشغّل عمليات بحث أو نشر تلقائي للاستراتيجيات"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E106",
    "name": "Parameter Optimization",
    "name_ar": "محرك Parameter Optimization",
    "group": "Backtesting & Learning",
    "status": "partial",
    "capabilities": [
      "اختيار أفضل تجربة معاملات من نتائج تحقق مزودة مع حد أدنى للعينات"
    ],
    "gaps": [
      "يتطلب تشغيل التجارب خارج هذا المحرك ولا يغير معاملات الإنتاج"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E107",
    "name": "Overfitting Detection",
    "name_ar": "محرك Overfitting Detection",
    "group": "Backtesting & Learning",
    "status": "partial",
    "capabilities": [
      "قياس فجوة أداء التدريب والتحقق"
    ],
    "gaps": [
      "يتطلب مقاييس تدريب وتحقق خارجية موثوقة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E108",
    "name": "Out-of-Sample Validation",
    "name_ar": "محرك Out-of-Sample Validation",
    "group": "Backtesting & Learning",
    "status": "partial",
    "capabilities": [
      "عرض مقاييس عينة اختبار مستقلة مقدمة للنظام"
    ],
    "gaps": [
      "لا ينشئ بنفسه مجموعة اختبار مستقلة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E109",
    "name": "Performance Attribution",
    "name_ar": "محرك Performance Attribution",
    "group": "Backtesting & Learning",
    "status": "partial",
    "capabilities": [
      "نسب صافي PnL إلى تسمية الاستراتيجية/مصدر الإشارة"
    ],
    "gaps": [
      "يتطلب تسجيل مصدر كل صفقة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E110",
    "name": "Win Rate Analytics",
    "name_ar": "محرك Win Rate Analytics",
    "group": "Backtesting & Learning",
    "status": "partial",
    "capabilities": [
      "حساب نسبة الصفقات الرابحة من الصفقات الورقية المغلقة"
    ],
    "gaps": [
      "يتطلب تاريخاً مغلقاً كافياً ولا يعكس أداءً مستقبلياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E111",
    "name": "Profit Factor",
    "name_ar": "محرك Profit Factor",
    "group": "Backtesting & Learning",
    "status": "partial",
    "capabilities": [
      "حساب Profit Factor من إجمالي الربح والخسارة المحققين"
    ],
    "gaps": [
      "غير معرّف عند عدم وجود خسائر ويحتاج عينة ممثلة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E112",
    "name": "Trade Expectancy",
    "name_ar": "محرك Trade Expectancy",
    "group": "Backtesting & Learning",
    "status": "partial",
    "capabilities": [
      "حساب متوسط صافي الربح أو الخسارة لكل صفقة مغلقة"
    ],
    "gaps": [
      "إحصاء وصفي حساس لحجم العينة وتوزيع النتائج"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E113",
    "name": "Strategy Comparison",
    "name_ar": "محرك Strategy Comparison",
    "group": "Backtesting & Learning",
    "status": "partial",
    "capabilities": [
      "مقارنة نتائج استراتيجيات مزودة حسب العائد والتراجع"
    ],
    "gaps": [
      "لا يجري تحسيناً أو ترقية تلقائية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E114",
    "name": "Model Drift Detection",
    "name_ar": "محرك Model Drift Detection",
    "group": "Backtesting & Learning",
    "status": "partial",
    "capabilities": [
      "كشف تغير مقاييس النموذج بين خط أساس ونافذة حديثة"
    ],
    "gaps": [
      "يتطلب مقاييس محفوظة ومقارنة متجانسة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E115",
    "name": "Continuous Learning",
    "name_ar": "محرك Continuous Learning",
    "group": "Backtesting & Learning",
    "status": "partial",
    "capabilities": [
      "تحديد جاهزية إعادة التدريب عند ظهور انحراف أو عينات موسومة كافية"
    ],
    "gaps": [
      "لا ينفذ تدريباً مستمراً أو استبدال نموذج دون مراجعة خارج العينة"
    ],
    "evidence": "partial_engine_runtime_adapter"
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
    "status": "partial",
    "capabilities": [
      "مراجعة حالة التأكيد مع موافقة المخاطر"
    ],
    "gaps": [
      "قراءة شرطية ولا تنفذ دخولاً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E119",
    "name": "Target Tracker",
    "name_ar": "محرك Target Tracker",
    "group": "Trade Management",
    "status": "partial",
    "capabilities": [
      "رصد وصول السعر لهدف أو وقف من علامات سعر مزودة"
    ],
    "gaps": [
      "مراقبة فقط ولا تغلق المركز آلياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E120",
    "name": "Stop Loss Monitor",
    "name_ar": "محرك Stop Loss Monitor",
    "group": "Trade Management",
    "status": "partial",
    "capabilities": [
      "مراقبة مستويات الوقف والأهداف للمراكز التجريبية"
    ],
    "gaps": [
      "تحتاج علامات أسعار حديثة موثوقة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E121",
    "name": "Smart Exit",
    "name_ar": "محرك Smart Exit",
    "group": "Trade Management",
    "status": "partial",
    "capabilities": [
      "مؤشرات خروج مبنية على مستوى الوقف والهدف"
    ],
    "gaps": [
      "لا يتخذ قرار خروج مستقل ولا يرسل أوامر"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E122",
    "name": "Partial Profit Taking",
    "name_ar": "محرك Partial Profit Taking",
    "group": "Trade Management",
    "status": "partial",
    "capabilities": [
      "إظهار وصول المراكز إلى مستويات أهداف جزئية"
    ],
    "gaps": [
      "لا ينفذ جني أرباح جزئي تلقائياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E123",
    "name": "Trade Recovery",
    "name_ar": "محرك Trade Recovery",
    "group": "Trade Management",
    "status": "partial",
    "capabilities": [
      "فحص سلامة سجل المراكز الورقية وتحديد بيانات الصفقة الناقصة"
    ],
    "gaps": [
      "فحص قراءة فقط ولا يعيد إنشاء الصفقات أو يغير سجل الحساب"
    ],
    "evidence": "partial_engine_runtime_adapter"
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
    "status": "partial",
    "capabilities": [
      "وكيل تحليل سوق حتمي يجمع الاتجاه والحجم والانضغاط"
    ],
    "gaps": [
      "ليس نموذج ذكاء توليدي ولا يملك تدريباً مستقلاً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E128",
    "name": "Liquidity Agent",
    "name_ar": "محرك Liquidity Agent",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "وكيل سيولة يقرأ عمق دفتر الأوامر واختلاله"
    ],
    "gaps": [
      "لقطة الدفتر قابلة للإلغاء والتغيير"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E129",
    "name": "Smart Money Agent",
    "name_ar": "محرك Smart Money Agent",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "وكيل Smart Money تجميعي من البنية والسحب والفجوات"
    ],
    "gaps": [
      "لا يحدد هوية المؤسسات أو أوامرها"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E130",
    "name": "Derivatives Agent",
    "name_ar": "محرك Derivatives Agent",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "وكيل مشتقات يقرأ OI والتمويل والتصفية عند توافرها"
    ],
    "gaps": [
      "تغطية مزود واحدة ولا تشمل كامل أسواق المشتقات"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E131",
    "name": "Technical Analysis Agent",
    "name_ar": "محرك Technical Analysis Agent",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "وكيل فني يعتمد الاتجاه والزخم ومؤشرات الشموع"
    ],
    "gaps": [
      "يعتمد قواعد قابلة للتفسير لا تنبؤاً احتماليّاً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E132",
    "name": "AI Prediction Agent",
    "name_ar": "محرك AI Prediction Agent",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "تجميع انحدار لوجستي وغابة عشوائية وتوقع مرجعي لاتجاه بحثي"
    ],
    "gaps": [
      "نماذج داخل نافذة الطلب غير معايرة ولا تمثل خدمة تنبؤ إنتاجية"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E133",
    "name": "Risk Officer Agent",
    "name_ar": "محرك Risk Officer Agent",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "وكيل مخاطرة يختبر شروط الخطة وحدودها"
    ],
    "gaps": [
      "موافقة نهائية تتطلب جميع مدخلات المخاطر"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E134",
    "name": "Strategy Manager Agent",
    "name_ar": "محرك Strategy Manager Agent",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "توجيه بحثي للاستراتيجية حسب نظام السوق"
    ],
    "gaps": [
      "لا يغير استراتيجية التداول تلقائياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E135",
    "name": "Decision Fusion",
    "name_ar": "محرك Decision Fusion",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "دمج تصويت الوكلاء المتاحين"
    ],
    "gaps": [
      "لا توجد أوزان أو تعلم لتصحيح موثوقية كل وكيل"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E136",
    "name": "Agent Disagreement",
    "name_ar": "محرك Agent Disagreement",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "كشف اختلاف اتجاهات الوكلاء وتحديد التعارض"
    ],
    "gaps": [
      "يتطلب مخرجات وكلاء مستقلة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E137",
    "name": "Consensus Engine",
    "name_ar": "محرك Consensus Engine",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "تجميع توافق اتجاهات الوكلاء"
    ],
    "gaps": [
      "تصويت غير معاير ولا يعادل احتمال النجاح"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E138",
    "name": "Knowledge Memory",
    "name_ar": "محرك Knowledge Memory",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "تلخيص أحداث الفرص المخزنة حسب نوع الحدث"
    ],
    "gaps": [
      "يتطلب سجل أحداث محفوظاً ومكتملًا"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E139",
    "name": "Adaptive Strategy Router",
    "name_ar": "محرك Adaptive Strategy Router",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "توجيه بحثي إلى نمط تحليل حسب نظام السوق"
    ],
    "gaps": [
      "لا يفعّل أو يروّج استراتيجيات آلياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E140",
    "name": "Autonomous Research",
    "name_ar": "محرك Autonomous Research",
    "group": "Multi-Agent Intelligence",
    "status": "partial",
    "capabilities": [
      "فرز مرشحي البحث حسب نتائج التحقق خارج العينة"
    ],
    "gaps": [
      "لا ينشر أو يرقّي استراتيجية تلقائياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E141",
    "name": "Scheduler",
    "name_ar": "محرك Scheduler",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "فحص تعريفات الوظائف المجدولة وفواصلها الزمنية وحالة backend"
    ],
    "gaps": [
      "لا يبدأ عاملاً مجدولاً دائماً؛ يحتاج ربط runtime scheduler"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E142",
    "name": "Event Bus",
    "name_ar": "محرك Event Bus",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "فحص عدادات نشر واستهلاك الأحداث وتقدير التراكم"
    ],
    "gaps": [
      "يتطلب عدادات Event Bus من الخدمة المشغلة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E143",
    "name": "Cache",
    "name_ar": "محرك Cache",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "فحص حالة cache من قياسات الخدمة المقدمة"
    ],
    "gaps": [
      "يتطلب تكوين Redis أو cache backend فعلي"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E144",
    "name": "Database",
    "name_ar": "محرك Database",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "فحص حالة قاعدة البيانات من بيانات صحة الخدمة المقدمة"
    ],
    "gaps": [
      "يتطلب ربط فحص اتصال PostgreSQL/TimescaleDB فعلي"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E145",
    "name": "WebSocket Manager",
    "name_ar": "محرك WebSocket Manager",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "فحص حالة WebSocket واتصالاته من مؤشرات الخدمة المقدمة"
    ],
    "gaps": [
      "يتطلب تكامل heartbeat وقياسات الاتصالات الفعلية"
    ],
    "evidence": "partial_engine_runtime_adapter"
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
    "status": "partial",
    "capabilities": [
      "تصنيف أعطال الخدمات إلى قابلة لإعادة المحاولة أو تحتاج مراجعة"
    ],
    "gaps": [
      "لا ينفذ إعادة التشغيل؛ سياسة التكرار موجودة بعميل المزود"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E149",
    "name": "Duplicate Signal Filter",
    "name_ar": "محرك Duplicate Signal Filter",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "إزالة تكرار الإشارات حسب الأصل والسوق والاتجاه ووقت الإشارة"
    ],
    "gaps": [
      "يتطلب هوية إشارة ثابتة وتخزيناً دائماً عبر عمليات إعادة التشغيل"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E150",
    "name": "Notification Engine",
    "name_ar": "محرك Notification Engine",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "إنشاء نوايا إشعار موحدة ومفحوصة مع مفاتيح منع التكرار"
    ],
    "gaps": [
      "لا يرسل الإشعارات ما لم يربط ناقل إشعارات فعلي"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E151",
    "name": "Audit Log",
    "name_ar": "محرك Audit Log",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "فحص سلامة معرفات سجلات التدقيق وتكرارها"
    ],
    "gaps": [
      "يتطلب سجلات أحداث دائمة ومتكاملة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E152",
    "name": "Model Registry",
    "name_ar": "محرك Model Registry",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "عرض بيانات إصدارات النماذج المسجلة"
    ],
    "gaps": [
      "لا يحمل ملفات النماذج أو ينشرها"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E153",
    "name": "Data Replay",
    "name_ar": "محرك Data Replay",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "ترتيب أحداث إعادة التشغيل التاريخي حسب الطابع الزمني"
    ],
    "gaps": [
      "يتطلب أحداثاً مخزنة مسبقاً ولا يسحب بيانات المنصات"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E154",
    "name": "Security Engine",
    "name_ar": "محرك Security Engine",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "فحص إعدادات الأمان المطلوبة والتأكد من Paper Only"
    ],
    "gaps": [
      "يعتمد على بيانات سياسة التشغيل المقدمة ولا يفحص قيم الأسرار أو إعدادات الاستضافة بذاته"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E155",
    "name": "Resource Manager",
    "name_ar": "محرك Resource Manager",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "فحص ضغط CPU والذاكرة من لقطة موارد التشغيل"
    ],
    "gaps": [
      "يتطلب قياسات من بيئة الاستضافة"
    ],
    "evidence": "partial_engine_runtime_adapter"
  },
  {
    "id": "E156",
    "name": "Watchdog",
    "name_ar": "محرك Watchdog",
    "group": "Infrastructure",
    "status": "partial",
    "capabilities": [
      "كشف الخدمات التي تجاوزت عمر نبضة الحياة المحدد"
    ],
    "gaps": [
      "تنبيه مراقبة فقط ولا يعيد تشغيل الخدمة تلقائياً"
    ],
    "evidence": "partial_engine_runtime_adapter"
  }
]

def engine_catalog(readiness: dict | None = None) -> dict:
    """Return declarations, or join them to request-time readiness evidence."""
    engines = [dict(item, capabilities=list(item.get("capabilities", [])),
                    gaps=list(item.get("gaps", []))) for item in ENGINE_CATALOG]
    statuses = ("implemented", "partial", "planned")
    counts = {status: sum(1 for item in engines if item["status"] == status) for status in statuses}
    if readiness:
        dynamic = {item["id"]: item for item in readiness.get("engines", [])}
        engines = [dict(item, **dynamic.get(item["id"], {})) for item in engines]
        counts = dict(readiness.get("counts", {}))
    groups = sorted({item["group"] for item in engines})
    group_counts = {group: sum(1 for item in engines if item["group"] == group) for group in groups}
    return {"name":"QUANT NEXUS","catalog_version":"1.9.0","total":len(engines),
            "counts":counts,"group_counts":group_counts,"engines":engines,
            "priority":"early_opportunity_detection","trading_mode":"simulation",
            "live_trading_enabled":False,"execution_capability":"paper_only",
            "disclaimer":"Statuses are request-time evidence when readiness is supplied. Catalogue declarations and documented limitations remain visible."}

