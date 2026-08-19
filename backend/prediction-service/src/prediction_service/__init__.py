"""EHOS prediction-service.

Local-first, governed, advisory forecasting for the nine PREDICTIVE_ANALYTICS
targets. The service trains candidates in-process (seasonal-naive / SES),
registers them in ``ai_db.ai_models`` with a ``model_evaluations`` verdict,
serves approved models into append-only ``ai_db.predictions`` rows and publishes
``PredictionGenerated`` on the event bus.
"""

__version__ = "0.1.0"