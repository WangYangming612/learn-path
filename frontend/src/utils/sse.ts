/**
 * SSE 流解析工具
 */

/**
 * 从 ReadableStream 解析 SSE（data: ...\n\n）
 */
export async function readSSEStream(
  body: ReadableStream<Uint8Array>,
  onData: (dataLine: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const abort = () => {
    void reader.cancel().catch(() => undefined);
  };
  signal?.addEventListener("abort", abort);

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let sep = buffer.indexOf("\n\n");
      while (sep >= 0) {
        const chunk = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);

        const dataLines: string[] = [];
        for (const line of chunk.split("\n")) {
          const trimmed = line.replace(/\r$/, "");
          if (trimmed.startsWith(":") || trimmed === "") continue;
          if (trimmed.startsWith("data:")) {
            dataLines.push(trimmed.slice(5).trimStart());
          }
        }
        if (dataLines.length > 0) {
          onData(dataLines.join("\n"));
        }

        sep = buffer.indexOf("\n\n");
      }
    }

    if (buffer.trim()) {
      const dataLines: string[] = [];
      for (const line of buffer.split("\n")) {
        const trimmed = line.replace(/\r$/, "");
        if (trimmed.startsWith("data:")) {
          dataLines.push(trimmed.slice(5).trimStart());
        }
      }
      if (dataLines.length > 0) {
        onData(dataLines.join("\n"));
      }
    }
  } finally {
    signal?.removeEventListener("abort", abort);
    reader.releaseLock();
  }
}
