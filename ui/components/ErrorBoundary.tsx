"use client";
import React from "react";

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  label?: string;
}

interface State { hasError: boolean; message: string }

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error?.message ?? "Unknown error" };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`[ErrorBoundary:${this.props.label ?? "unknown"}]`, error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    if (this.props.fallback) return this.props.fallback;
    return (
      <div style={{
        padding: "16px 20px",
        background: "rgba(239,68,68,0.05)",
        border: "1px solid rgba(239,68,68,0.15)",
        borderRadius: 12,
        fontSize: 12,
        color: "rgba(255,255,255,0.5)",
      }}>
        <p style={{ fontWeight: 600, color: "var(--red)", marginBottom: 4 }}>
          {this.props.label ?? "Component"} failed to render
        </p>
        <p style={{ fontFamily: "monospace", fontSize: 11 }}>{this.state.message}</p>
        <button
          onClick={() => this.setState({ hasError: false, message: "" })}
          style={{
            marginTop: 10, padding: "5px 12px", borderRadius: 7, fontSize: 11,
            background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)",
            color: "rgba(255,255,255,0.5)", cursor: "pointer",
          }}
        >
          Retry
        </button>
      </div>
    );
  }
}
