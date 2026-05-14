# ml_predictor_dashboard.py - Agricultural Standards Version
import sys
import json
import joblib
import numpy as np
import pandas as pd
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(SCRIPT_DIR, 'saved_models')

print("🌱 Agricultural ML Predictor started", file=sys.stderr)

# Load dashboard-specific models
try:
    temp_model = joblib.load(os.path.join(MODEL_DIR, 'dashboard_temp_model.pkl'))
    temp_scaler = joblib.load(os.path.join(MODEL_DIR, 'dashboard_temp_scaler.pkl'))
    temp_features = joblib.load(os.path.join(MODEL_DIR, 'dashboard_temp_features.pkl'))
    print("✅ Loaded temperature prediction model", file=sys.stderr)
except Exception as e:
    temp_model = None
    print(f"⚠️ Temperature model not found: {e}", file=sys.stderr)

try:
    tds_model = joblib.load(os.path.join(MODEL_DIR, 'dashboard_tds_model.pkl'))
    tds_scaler = joblib.load(os.path.join(MODEL_DIR, 'dashboard_tds_scaler.pkl'))
    tds_features = joblib.load(os.path.join(MODEL_DIR, 'dashboard_tds_features.pkl'))
    print("✅ Loaded TDS prediction model", file=sys.stderr)
except Exception as e:
    tds_model = None
    print(f"⚠️ TDS model not found: {e}", file=sys.stderr)

# Load agricultural classification models
try:
    agri_qual_model = joblib.load(os.path.join(MODEL_DIR, 'agri_quality_model.pkl'))
    agri_qual_scaler = joblib.load(os.path.join(MODEL_DIR, 'agri_quality_scaler.pkl'))
    agri_qual_encoder = joblib.load(os.path.join(MODEL_DIR, 'agri_quality_encoder.pkl'))
    agri_qual_features = joblib.load(os.path.join(MODEL_DIR, 'agri_quality_features.pkl'))
    print("✅ Loaded agricultural quality model", file=sys.stderr)
except Exception as e:
    agri_qual_model = None
    print(f"⚠️ Agricultural quality model not found: {e}", file=sys.stderr)

try:
    agri_temp_model = joblib.load(os.path.join(MODEL_DIR, 'agri_temp_model.pkl'))
    agri_temp_scaler = joblib.load(os.path.join(MODEL_DIR, 'agri_temp_scaler.pkl'))
    agri_temp_encoder = joblib.load(os.path.join(MODEL_DIR, 'agri_temp_encoder.pkl'))
    print("✅ Loaded agricultural temperature category model", file=sys.stderr)
except Exception as e:
    agri_temp_model = None
    print(f"⚠️ Agricultural temperature model not found: {e}", file=sys.stderr)

def get_temperature_category_rule_based(temp):
    """Rule-based temperature classification using your scale"""
    if temp < 5:
        return "❌ Bad (Very Poor Growth)"
    elif temp < 10:
        return "⚠️ Weak (Poor Growth)"
    elif temp < 15:
        return "😐 Fair (Moderate Growth)"
    elif temp < 25:
        return "✅ Good"
    elif temp < 35:
        return "🌟 Excellent (Optimal Growth)"
    else:
        return "🔥 Bad (Heat Stress)"

def get_quality_rule_based(tds):
    """Rule-based water quality classification using your scale"""
    if tds < 300:
        return "🌟 Excellent"
    elif tds < 700:
        return "✅ Good"
    elif tds < 1500:
        return "😐 Fair"
    elif tds < 3000:
        return "⚠️ Poor"
    else:
        return "❌ Bad"

def get_quality_description(quality):
    """Get the full description for each quality level"""
    descriptions = {
        "🌟 Excellent": "🌟 Excellent (<300 ppm) - Ideal for seedlings & sensitive crops",
        "✅ Good": "✅ Good (300-700 ppm) - Safe for most crops",
        "😐 Fair": "😐 Fair (700-1500 ppm) - Slight salt stress, salt-tolerant crops ok",
        "⚠️ Poor": "⚠️ Poor (1500-3000 ppm) - Clear stress, leaf burn possible",
        "❌ Bad": "❌ Bad (>3000 ppm) - High salinity, most crops fail"
    }
    return descriptions.get(quality, quality)

def prepare_features(data, feature_list):
    """Prepare feature vector for prediction"""
    now = datetime.now()
    
    feature_dict = {}
    for feature in feature_list:
        if feature == 'hour':
            feature_dict[feature] = now.hour
        elif feature == 'day_of_week':
            feature_dict[feature] = now.weekday()
        elif feature in data:
            feature_dict[feature] = data[feature]
        else:
            # Default values
            defaults = {
                'temperature': 20.0,
                'humidity': 50.0,
                'pressure': 1013.0,
                'altitude': 100.0,
                'tds_ppm': 100.0,
                'uv_index': 0.0,
                'eco2': 400.0,
                'tvoc': 0.0,
                'rssi': -50.0,
                'snr': 10.0
            }
            feature_dict[feature] = defaults.get(feature, 0.0)
    
    return pd.DataFrame([feature_dict])

print("✅ Ready! Waiting for agricultural data...", file=sys.stderr)

while True:
    try:
        line = sys.stdin.readline()
        if not line:
            break
            
        data = json.loads(line.strip())
        
        result = {
            'temp_prediction': None,
            'tds_prediction': None,
            'temp_category': None,
            'quality_prediction': None,
            'quality_description': None,
            'timestamp': data.get('ts', int(datetime.now().timestamp() * 1000))
        }
        
        # Make temperature prediction
        if temp_model is not None:
            try:
                features = prepare_features(data, temp_features)
                features_scaled = temp_scaler.transform(features)
                pred = temp_model.predict(features_scaled)[0]
                result['temp_prediction'] = float(pred)
                
                # Get temperature category for the prediction
                result['temp_category'] = get_temperature_category_rule_based(pred)
            except Exception as e:
                print(f"⚠️ Temp prediction error: {e}", file=sys.stderr)
        
        # Make TDS prediction
        if tds_model is not None:
            try:
                features = prepare_features(data, tds_features)
                features_scaled = tds_scaler.transform(features)
                pred = tds_model.predict(features_scaled)[0]
                result['tds_prediction'] = float(pred)
                
                # Get quality based on TDS prediction
                result['quality_prediction'] = get_quality_rule_based(pred)
                result['quality_description'] = get_quality_description(result['quality_prediction'])
            except Exception as e:
                print(f"⚠️ TDS prediction error: {e}", file=sys.stderr)
        
        # Also classify current conditions (using actual readings)
        current_temp = data.get('temp')
        current_tds = data.get('tds')
        
        if current_temp is not None:
            result['current_temp_category'] = get_temperature_category_rule_based(current_temp)
        
        if current_tds is not None:
            result['current_quality'] = get_quality_rule_based(current_tds)
            result['quality_description'] = get_quality_description(result['current_quality'])
        
        print(json.dumps(result))
        sys.stdout.flush()
        
    except Exception as e:
        print(json.dumps({'error': str(e)}), file=sys.stderr)
        sys.stdout.flush()
