'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type { Command, CommandResult, OperatorService, Scenario, WorkspaceState } from './domain';
import { createMockOperatorService } from './mock-service';

interface OperatorContextValue {
  state: WorkspaceState | null;
  loading: boolean;
  error: string | null;
  execute: (command: Command) => Promise<CommandResult>;
  reset: (scenario?: Scenario) => Promise<void>;
  notice: CommandResult | null;
  dismissNotice: () => void;
}
const OperatorContext = createContext<OperatorContextValue | null>(null);
export function OperatorProvider({
  children,
  service: provided,
}: {
  children: ReactNode;
  service?: OperatorService;
}) {
  const service = useRef<OperatorService | null>(null);
  const [state, setState] = useState<WorkspaceState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<CommandResult | null>(null);
  useEffect(() => {
    let storage: Storage | undefined;
    try {
      storage = window.localStorage;
    } catch {
      /* Service keeps an in-memory workspace. */
    }
    const adapter = provided ?? createMockOperatorService({ storage });
    service.current = adapter;
    let live = true;
    const unsubscribe = adapter.subscribe((next) => {
      if (live) setState(next);
    });
    adapter
      .load()
      .then((next) => {
        if (live) setState(next);
      })
      .catch((err) => {
        if (live) setError(String(err));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
      unsubscribe();
      adapter.dispose();
    };
  }, [provided]);
  const execute = useCallback(async (command: Command): Promise<CommandResult> => {
    if (!service.current)
      return { ok: false, kind: 'failed', message: 'The demo is still loading.' };
    try {
      const result = await service.current.execute(command);
      if (result.ok) setState(result.state);
      if (command.type !== 'updateDraft' || !result.ok) setNotice(result);
      return result;
    } catch {
      const result: CommandResult = {
        ok: false,
        kind: 'failed',
        message: 'The simulated service could not complete that action. Try again.',
      };
      setNotice(result);
      return result;
    }
  }, []);
  const reset = useCallback(async (scenario: Scenario = 'portfolio') => {
    if (!service.current) return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      setState(await service.current.reset(scenario));
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);
  return (
    <OperatorContext.Provider
      value={{
        state,
        loading,
        error,
        execute,
        reset,
        notice,
        dismissNotice: () => setNotice(null),
      }}
    >
      {children}
    </OperatorContext.Provider>
  );
}
export function useOperator() {
  const value = useContext(OperatorContext);
  if (!value) throw new Error('OperatorProvider is required.');
  return value;
}
