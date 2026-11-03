"use client";

import { useEffect, useState } from "react";
import { isAppError, type AppError } from "@/lib/api/client";

type AsyncState<T> = { data: T | null; error: AppError | null; loading: boolean };

/**
 * 页面拉取服务端数据的最小钩子：loading / error / 数据 三态分开（手册 9.3）。
 * 不用 TanStack Query（《前端适配声明》§6）；点「重新加载」时重新向后端取真实状态。
 * 要求 loader 是模块级稳定函数（不要在渲染里新建箭头函数）。
 */
export function useAsync<T>(loader: () => Promise<T>) {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    loader()
      .then((data) => {
        if (alive) setState({ data, error: null, loading: false });
      })
      .catch((err: unknown) => {
        if (alive) setState({ data: null, error: isAppError(err) ? err : null, loading: false });
      });
    return () => {
      alive = false;
    };
  }, [loader, tick]);

  const reload = () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    setTick((value) => value + 1);
  };

  return { ...state, reload };
}
