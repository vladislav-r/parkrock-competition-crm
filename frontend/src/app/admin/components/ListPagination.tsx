"use client";

import { useState } from "react";
import "./list-pagination.css";

export function usePagination(total: number, resetKey = "") {
  const [state, setState] = useState({ key: resetKey, page: 1, pageSize: 50 });
  if (state.key !== resetKey) setState({ ...state, key: resetKey, page: 1 });
  const pages = Math.max(1, Math.ceil(total / state.pageSize));
  const page = state.key === resetKey ? Math.min(state.page, pages) : 1;
  return {
    total, page, pages, pageSize: state.pageSize, offset: (page - 1) * state.pageSize,
    onPageChange: (value: number) => setState({ ...state, key: resetKey, page: Math.max(1, Math.min(value, pages)) }),
    onPageSizeChange: (value: number) => setState({ key: resetKey, page: 1, pageSize: value }),
  };
}

export function ListPagination({ total, page, pages, pageSize, onPageChange, onPageSizeChange, label, busy = false }: ReturnType<typeof usePagination> & { label: string; busy?: boolean }) {
  return <nav data-view-action className="list-pagination" aria-label={`Страницы: ${label}`} aria-busy={busy}>
    <span role="status">{total ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)}` : "0"} из {total}</span>
    <label>По <select data-view-action aria-label={`Записей на странице: ${label}`} value={pageSize} disabled={busy} onChange={event => onPageSizeChange(Number(event.target.value))}>{[25, 50, 100].map(size => <option key={size} value={size}>{size}</option>)}</select></label>
    <div className="list-pagination-buttons">
      <button data-view-action type="button" aria-label="Первая страница" disabled={busy || page === 1} onClick={() => onPageChange(1)}>«</button>
      <button data-view-action type="button" aria-label="Предыдущая страница" disabled={busy || page === 1} onClick={() => onPageChange(page - 1)}>‹</button>
      <span>{page} / {pages}</span>
      <button data-view-action type="button" aria-label="Следующая страница" disabled={busy || page === pages} onClick={() => onPageChange(page + 1)}>›</button>
      <button data-view-action type="button" aria-label="Последняя страница" disabled={busy || page === pages} onClick={() => onPageChange(pages)}>»</button>
    </div>
  </nav>;
}
