"use client";

import { useState } from "react";
import { connectDatabase, errMsg, type ConnectDBPayload } from "@/lib/api";
import type { DatasetDetail } from "@/types/dataset";

export default function ConnectDatabaseDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (dataset: DatasetDetail) => void;
}) {
  const [dbType, setDbType] = useState<"postgres" | "mysql" | "sqlite">(
    "postgres",
  );
  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [database, setDatabase] = useState("");
  const [schema, setSchema] = useState("public");
  const [table, setTable] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isSqlite = dbType === "sqlite";

  async function handleConnect() {
    if (!name.trim() || !table.trim()) {
      setError("请填写数据集名称与表名");
      return;
    }
    if (!isSqlite && !database.trim()) {
      setError("请填写数据库名");
      return;
    }
    setLoading(true);
    setError(null);
    const payload: ConnectDBPayload = {
      name: name.trim(),
      db_type: dbType,
      host: isSqlite ? null : host || null,
      port: isSqlite ? null : port ? Number(port) : null,
      username: isSqlite ? null : username || null,
      password: isSqlite ? null : password || null,
      database: database || null,
      schema: dbType === "postgres" ? schema || "public" : null,
      table: table.trim(),
    };
    try {
      const d = await connectDatabase(payload);
      onCreated(d);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="card max-h-[90vh] w-full max-w-lg overflow-auto p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-bold text-ink">连接数据库</h2>
          <button
            className="text-faint transition hover:text-ink"
            onClick={onClose}
            aria-label="关闭"
          >
            ✕
          </button>
        </div>
        <p className="mt-1 text-xs text-faint">
          连接后，指定表会被物化为可分析的数据集（与上传文件等效）。连接密码仅保存在服务端，不会返回给前端。
        </p>

        <div className="mt-4 space-y-3">
          <div>
            <label className="eyebrow">数据库类型</label>
            <div className="mt-1 flex gap-2">
              {(["postgres", "mysql", "sqlite"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setDbType(t)}
                  className={`rounded-full border px-3 py-1 text-xs transition ${
                    dbType === t
                      ? "border-accent bg-accent-soft/50 text-ink"
                      : "border-line text-faint hover:border-line-strong"
                  }`}
                >
                  {t === "postgres"
                    ? "PostgreSQL"
                    : t === "mysql"
                      ? "MySQL"
                      : "SQLite"}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="eyebrow">数据集名称</label>
            <input
              className="input mt-1 w-full"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：生产订单表"
            />
          </div>

          {!isSqlite && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="eyebrow">主机</label>
                <input
                  className="input mt-1 w-full"
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="localhost"
                />
              </div>
              <div>
                <label className="eyebrow">端口</label>
                <input
                  className="input mt-1 w-full"
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                  placeholder={dbType === "postgres" ? "5432" : "3306"}
                />
              </div>
              <div>
                <label className="eyebrow">用户名</label>
                <input
                  className="input mt-1 w-full"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="postgres"
                />
              </div>
              <div>
                <label className="eyebrow">密码</label>
                <input
                  type="password"
                  className="input mt-1 w-full"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••"
                />
              </div>
            </div>
          )}

          <div>
            <label className="eyebrow">
              {isSqlite ? "SQLite 文件路径" : "数据库名"}
            </label>
            <input
              className="input mt-1 w-full"
              value={database}
              onChange={(e) => setDatabase(e.target.value)}
              placeholder={isSqlite ? "C:/data/app.db" : "mydb"}
            />
          </div>

          {dbType === "postgres" && (
            <div>
              <label className="eyebrow">Schema</label>
              <input
                className="input mt-1 w-full"
                value={schema}
                onChange={(e) => setSchema(e.target.value)}
                placeholder="public"
              />
            </div>
          )}

          <div>
            <label className="eyebrow">表名</label>
            <input
              className="input mt-1 w-full"
              value={table}
              onChange={(e) => setTable(e.target.value)}
              placeholder="orders"
            />
          </div>

          {error && (
            <p className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
              {error}
            </p>
          )}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose}>
            取消
          </button>
          <button
            className="btn btn-primary"
            onClick={handleConnect}
            disabled={loading}
          >
            {loading ? "连接中…" : "连接并导入"}
          </button>
        </div>
      </div>
    </div>
  );
}
