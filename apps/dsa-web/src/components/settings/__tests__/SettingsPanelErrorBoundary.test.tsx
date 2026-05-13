import { render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SettingsPanelErrorBoundary } from '../SettingsPanelErrorBoundary';

function ThrowingPanel(): ReactElement {
  throw new Error('mock settings panel crash');
}

describe('SettingsPanelErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders a diagnostic desktop-log fallback when a settings panel throws', () => {
    render(
      <SettingsPanelErrorBoundary title="通知设置" resetKey="notification">
        <ThrowingPanel />
      </SettingsPanelErrorBoundary>
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('通知设置加载失败')).toBeInTheDocument();
    expect(screen.getByText('desktop.log')).toBeInTheDocument();
    expect(screen.getByText(/release 版本、Windows 版本和触发入口/)).toBeInTheDocument();
    expect(screen.getByText(/错误摘要：mock settings panel crash/)).toBeInTheDocument();
  });

  it('resets after resetKey changes so the panel can render again', async () => {
    const { rerender } = render(
      <SettingsPanelErrorBoundary title="Agent 设置" resetKey="agent:v1">
        <ThrowingPanel />
      </SettingsPanelErrorBoundary>
    );

    expect(screen.getByText('Agent 设置加载失败')).toBeInTheDocument();

    rerender(
      <SettingsPanelErrorBoundary title="Agent 设置" resetKey="agent:v2">
        <div>Agent 设置已恢复</div>
      </SettingsPanelErrorBoundary>
    );

    await waitFor(() => {
      expect(screen.getByText('Agent 设置已恢复')).toBeInTheDocument();
    });
    expect(screen.queryByText('Agent 设置加载失败')).not.toBeInTheDocument();
  });
});
