"""Module 6 – Machine Learning Assistant.

Auto-detects whether the chosen target implies a classification or regression
problem, builds a preprocessing + model pipeline, trains/evaluates several
algorithms and presents the metrics (accuracy, precision, recall, F1, confusion
matrix for classification; R², MAE, RMSE for regression).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from utils import get_logger, load_config
from utils.helpers import categorical_columns, numeric_columns
from utils.ui import insight, kpi_cards, page_banner, require_data, section_header

logger = get_logger(__name__)
cfg = load_config()

# XGBoost is optional; fall back to sklearn gradient boosting if it is missing
# OR if its native library fails to load (e.g. missing OpenMP runtime on macOS).
try:
    from xgboost import XGBClassifier, XGBRegressor  # type: ignore

    _HAS_XGB = True
except Exception:  # noqa: BLE001  - ImportError or XGBoostError (native lib)
    from sklearn.ensemble import (
        GradientBoostingClassifier as XGBClassifier,
        GradientBoostingRegressor as XGBRegressor,
    )

    _HAS_XGB = False


def _infer_problem_type(series: pd.Series) -> str:
    """Heuristically decide classification vs regression for a target column."""
    if series.dtype == object or str(series.dtype) == "category":
        return "classification"
    nunique = series.nunique(dropna=True)
    if nunique <= 15 and series.dropna().apply(float.is_integer if series.dtype == float else lambda _: True).all():
        # Few discrete integer-like values -> treat as classification.
        return "classification" if nunique <= 10 else "regression"
    return "regression"


def _build_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    """Build a column transformer scaling numerics & one-hot encoding categoricals."""
    num = X.select_dtypes(include=np.number).columns.tolist()
    cat = X.select_dtypes(exclude=np.number).columns.tolist()
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), num),
            ("cat", OneHotEncoder(handle_unknown="ignore", max_categories=20), cat),
        ],
        remainder="drop",
    )


def _models(problem: str) -> dict:
    """Return the candidate models for the detected problem type."""
    if problem == "classification":
        return {
            "Logistic Regression": LogisticRegression(max_iter=1000),
            "Random Forest": RandomForestClassifier(n_estimators=200, random_state=42),
            f"{'XGBoost' if _HAS_XGB else 'Gradient Boosting'}": XGBClassifier(random_state=42),
        }
    return {
        "Linear Regression": LinearRegression(),
        "Random Forest": RandomForestRegressor(n_estimators=200, random_state=42),
        f"{'XGBoost' if _HAS_XGB else 'Gradient Boosting'}": XGBRegressor(random_state=42),
    }


def render() -> None:
    """Render the ML Assistant page."""
    page_banner(
        "🧠", "Machine Learning Assistant",
        "Auto-detects the problem type, trains models and reports metrics.",
    )
    if not require_data():
        return

    df: pd.DataFrame = st.session_state["df"]
    all_cols = df.columns.tolist()

    target = st.selectbox("🎯 Target column to predict", all_cols)
    problem = _infer_problem_type(df[target])
    forced = st.radio("Problem type", ["Auto-detected", "Classification", "Regression"],
                      horizontal=True)
    if forced != "Auto-detected":
        problem = forced.lower()

    insight(f"Detected problem type: <b>{problem.title()}</b>.", "info")

    feature_options = [c for c in all_cols if c != target]
    features = st.multiselect("Feature columns", feature_options,
                              default=feature_options[:10])
    test_size = st.slider("Test set size (%)", 10, 40, 20) / 100

    if not features:
        st.warning("Select at least one feature column.")
        return

    if not st.button("🚀 Train Models", type="primary"):
        return

    try:
        results = _train_and_evaluate(df, features, target, problem, test_size)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Training failed: {exc}")
        logger.exception("ML training failed")
        return

    _render_results(results, problem)


def _train_and_evaluate(df, features, target, problem, test_size) -> dict:
    """Train candidate models and collect metrics. Persists the best model."""
    data = df[features + [target]].dropna()
    X, y = data[features], data[target]

    stratify = y if problem == "classification" and y.nunique() > 1 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=stratify
    )

    pre = _build_preprocessor(X)
    leaderboard: list[dict] = []
    best_pipeline = None
    best_score = -np.inf
    artifacts: dict = {}

    # Choose a safe number of CV folds (>=2, <= smallest class / 5).
    if problem == "classification":
        min_class = int(y.value_counts().min())
        cv_folds = max(2, min(5, min_class))
        scoring = "accuracy"
    else:
        cv_folds = min(5, max(2, len(X_train) // 50))
        scoring = "r2"

    for name, model in _models(problem).items():
        pipe = Pipeline([("pre", pre), ("model", model)])
        pipe.fit(X_train, y_train)
        preds = pipe.predict(X_test)

        # K-fold cross-validation for a robust generalisation estimate.
        try:
            cv_scores = cross_val_score(pipe, X, y, cv=cv_folds, scoring=scoring)
            cv_mean, cv_std = float(cv_scores.mean()), float(cv_scores.std())
        except Exception:  # noqa: BLE001
            cv_mean, cv_std = float("nan"), float("nan")

        if problem == "classification":
            score = accuracy_score(y_test, preds)
            row = {
                "Model": name,
                "Accuracy": round(score, 4),
                "Precision": round(precision_score(y_test, preds, average="weighted", zero_division=0), 4),
                "Recall": round(recall_score(y_test, preds, average="weighted", zero_division=0), 4),
                "F1": round(f1_score(y_test, preds, average="weighted", zero_division=0), 4),
                f"CV Acc ({cv_folds}-fold)": f"{cv_mean:.3f} ± {cv_std:.3f}",
            }
        else:
            score = r2_score(y_test, preds)
            rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
            row = {
                "Model": name,
                "R²": round(score, 4),
                "MAE": round(mean_absolute_error(y_test, preds), 4),
                "RMSE": round(rmse, 4),
                f"CV R² ({cv_folds}-fold)": f"{cv_mean:.3f} ± {cv_std:.3f}",
            }
        leaderboard.append(row)

        if score > best_score:
            best_score = score
            best_pipeline = pipe
            # Capture probabilities for ROC if available (classification).
            proba = None
            if problem == "classification" and hasattr(pipe, "predict_proba"):
                try:
                    proba = pipe.predict_proba(X_test)
                except Exception:  # noqa: BLE001
                    proba = None
            artifacts = {"name": name, "preds": preds, "y_test": y_test,
                         "proba": proba, "cv_mean": cv_mean, "cv_folds": cv_folds}

    # Persist best model for reproducibility.
    try:
        import joblib

        model_path = cfg.models_dir / "best_model.joblib"
        joblib.dump(best_pipeline, model_path)
        logger.info("Saved best model (%s) to %s", artifacts["name"], model_path)
    except Exception:  # noqa: BLE001
        logger.warning("Could not persist model", exc_info=True)

    return {
        "leaderboard": pd.DataFrame(leaderboard),
        "best_name": artifacts["name"],
        "preds": artifacts["preds"],
        "y_test": artifacts["y_test"],
        "proba": artifacts.get("proba"),
        "cv_mean": artifacts.get("cv_mean", float("nan")),
        "cv_folds": artifacts.get("cv_folds", 5),
        "pipeline": best_pipeline,
        "features": features,
    }


def _render_results(results: dict, problem: str) -> None:
    """Render leaderboard, best-model metrics and diagnostic plots."""
    st.success(f"✅ Best model: **{results['best_name']}**")
    section_header("Model Leaderboard")
    st.dataframe(results["leaderboard"], use_container_width=True, hide_index=True)

    y_test, preds = results["y_test"], results["preds"]

    if problem == "classification":
        acc = accuracy_score(y_test, preds)
        prec = precision_score(y_test, preds, average="weighted", zero_division=0)
        rec = recall_score(y_test, preds, average="weighted", zero_division=0)
        f1 = f1_score(y_test, preds, average="weighted", zero_division=0)
        cards = [
            {"label": "Accuracy", "value": f"{acc:.3f}"},
            {"label": "Precision", "value": f"{prec:.3f}"},
            {"label": "Recall", "value": f"{rec:.3f}"},
            {"label": "F1 Score", "value": f"{f1:.3f}"},
            {"label": f"CV Accuracy ({results['cv_folds']}-fold)", "value": f"{results['cv_mean']:.3f}"},
        ]
        # ROC-AUC for binary problems with probabilities available.
        roc_auc = None
        proba = results.get("proba")
        labels = sorted(pd.unique(y_test))
        if proba is not None and len(labels) == 2:
            try:
                roc_auc = roc_auc_score((y_test == labels[1]).astype(int), proba[:, 1])
                cards.append({"label": "ROC-AUC", "value": f"{roc_auc:.3f}"})
            except Exception:  # noqa: BLE001
                roc_auc = None
        kpi_cards(cards)

        # Headline metric gauge.
        _metric_gauge("F1 Score", f1)

        c1, c2 = st.columns(2)
        with c1:
            section_header("Confusion Matrix")
            cm = confusion_matrix(y_test, preds, labels=labels)
            fig = px.imshow(cm, text_auto=True, x=[str(l) for l in labels],
                            y=[str(l) for l in labels], color_continuous_scale="Blues",
                            labels=dict(x="Predicted", y="Actual"), title="Confusion Matrix")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            if roc_auc is not None:
                section_header("ROC Curve")
                fpr, tpr, _ = roc_curve((y_test == labels[1]).astype(int), proba[:, 1])
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=fpr, y=tpr, mode="lines",
                                         name=f"ROC (AUC={roc_auc:.3f})",
                                         line=dict(color="#22D3EE", width=3)))
                fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines",
                                         line=dict(dash="dash", color="#64748B"),
                                         name="Random"))
                fig.update_layout(title="ROC Curve", xaxis_title="False Positive Rate",
                                  yaxis_title="True Positive Rate")
                st.plotly_chart(fig, use_container_width=True)
            else:
                section_header("Per-Class Performance")
                report = classification_report(y_test, preds, output_dict=True, zero_division=0)
                rep_df = pd.DataFrame(report).T.round(3)
                st.dataframe(rep_df, use_container_width=True)

        # Always show the per-class breakdown (precision/recall/F1 per label).
        with st.expander("📋 Detailed classification report (per class)"):
            report = classification_report(y_test, preds, output_dict=True, zero_division=0)
            st.dataframe(pd.DataFrame(report).T.round(3), use_container_width=True)
    else:
        rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
        r2 = r2_score(y_test, preds)
        kpi_cards([
            {"label": "R² Score", "value": f"{r2:.3f}"},
            {"label": "MAE", "value": f"{mean_absolute_error(y_test, preds):,.3f}"},
            {"label": "RMSE", "value": f"{rmse:,.3f}"},
            {"label": f"CV R² ({results['cv_folds']}-fold)", "value": f"{results['cv_mean']:.3f}"},
        ])
        _metric_gauge("R² Score", max(0.0, r2))
        section_header("Predicted vs Actual")
        scatter_df = pd.DataFrame({"Actual": y_test, "Predicted": preds})
        fig = px.scatter(scatter_df, x="Actual", y="Predicted", opacity=0.6,
                         title="Predicted vs Actual")
        lo, hi = float(np.min(y_test)), float(np.max(y_test))
        fig.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi,
                      line=dict(dash="dash", color="#DC2626"))
        st.plotly_chart(fig, use_container_width=True)

    # Feature importance when available.
    _render_feature_importance(results)


def _metric_gauge(label: str, value: float) -> None:
    """Render a neon gauge (0–1) for a headline model metric."""
    value = float(max(0.0, min(1.0, value)))
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number=dict(valueformat=".3f", font=dict(size=34, color="#F8FAFC")),
        title=dict(text=label, font=dict(size=15, color="#94A3B8")),
        gauge=dict(
            axis=dict(range=[0, 1], tickcolor="#64748B"),
            bar=dict(color="#22D3EE", thickness=0.28),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=[
                dict(range=[0, 0.6], color="rgba(244,63,94,0.18)"),
                dict(range=[0.6, 0.8], color="rgba(251,191,36,0.18)"),
                dict(range=[0.8, 1.0], color="rgba(52,211,153,0.20)"),
            ],
            threshold=dict(line=dict(color="#6366F1", width=4), thickness=0.8, value=value),
        ),
    ))
    fig.update_layout(height=240, margin=dict(l=20, r=20, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def _render_feature_importance(results: dict) -> None:
    """Show feature importances / coefficients if the model exposes them."""
    try:
        pipe = results["pipeline"]
        model = pipe.named_steps["model"]
        pre = pipe.named_steps["pre"]
        feature_names = pre.get_feature_names_out()
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
        elif hasattr(model, "coef_"):
            importances = np.abs(np.ravel(model.coef_))
        else:
            return
        imp_df = (
            pd.DataFrame({"Feature": feature_names, "Importance": importances})
            .sort_values("Importance", ascending=False).head(15)
        )
        section_header("Feature Importance")
        fig = px.bar(imp_df, x="Importance", y="Feature", orientation="h",
                     title="Top features")
        fig.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
    except Exception:  # noqa: BLE001
        logger.debug("Feature importance unavailable", exc_info=True)
