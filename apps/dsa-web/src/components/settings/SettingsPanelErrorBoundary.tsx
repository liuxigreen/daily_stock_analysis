import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { InlineAlert } from '../common';
import { cn } from '../../utils/cn';

interface SettingsPanelErrorBoundaryProps {
  title: string;
  children: ReactNode;
  resetKey?: string | number;
  className?: string;
}

interface SettingsPanelErrorBoundaryState {
  hasError: boolean;
  errorMessage: string;
}

export class SettingsPanelErrorBoundary extends Component<
  SettingsPanelErrorBoundaryProps,
  SettingsPanelErrorBoundaryState
> {
  override state: SettingsPanelErrorBoundaryState = {
    hasError: false,
    errorMessage: '',
  };

  static getDerivedStateFromError(error: unknown): SettingsPanelErrorBoundaryState {
    return {
      hasError: true,
      errorMessage: error instanceof Error ? error.message : '未知前端运行时异常',
    };
  }

  override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`Settings panel runtime error: ${this.props.title}`, error, errorInfo);
  }

  override componentDidUpdate(prevProps: SettingsPanelErrorBoundaryProps) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, errorMessage: '' });
    }
  }

  override render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className={cn('rounded-[1.5rem] border settings-border bg-card/94 p-5 shadow-soft-card-strong backdrop-blur-sm', this.props.className)}>
        <InlineAlert
          title={`${this.props.title}加载失败`}
          variant="danger"
          message={(
            <div className="space-y-2">
              <p>
                该设置区域发生前端运行时异常，页面其他设置仍可继续使用。请查看并提供桌面端日志
                <code className="mx-1 rounded bg-background/45 px-1 py-0.5 font-mono text-xs">desktop.log</code>
                ，同时补充 release 版本、Windows 版本和触发入口。
              </p>
              {this.state.errorMessage ? (
                <p className="break-words font-mono text-xs opacity-80">
                  错误摘要：{this.state.errorMessage}
                </p>
              ) : null}
            </div>
          )}
        />
      </div>
    );
  }
}
