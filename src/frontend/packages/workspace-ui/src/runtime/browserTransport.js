import { fetchEventSource } from '@microsoft/fetch-event-source';

export function createScopedStorage(namespace, storage = window.localStorage) {
  if (!namespace) throw new Error('A workspace storage namespace is required.');
  return {
    getItem: key => storage.getItem(`${namespace}:${key}`),
    setItem: (key, value) => storage.setItem(`${namespace}:${key}`, value),
    removeItem: key => storage.removeItem(`${namespace}:${key}`),
  };
}

export function createBrowserTransport({ baseUrl = '', headers = () => ({}), resourceUrl = path => path } = {}) {
  let scope = new AbortController();
  const address = path => `${baseUrl}${path}`;
  async function request(path, options = {}) {
    const merged = new Headers(await headers());
    new Headers(options.headers).forEach((value, name) => merged.set(name, value));
    return fetch(address(path), {
      ...options, headers: merged, credentials: 'same-origin',
      signal: options.signal ? AbortSignal.any([scope.signal, options.signal]) : scope.signal,
    });
  }
  function subscribe(path) {
    const controller = new AbortController();
    const listeners = new Map();
    const connection = {
      readyState: 0,
      onerror: null,
      addEventListener(name, callback) {
        if (!listeners.has(name)) listeners.set(name, new Set());
        listeners.get(name).add(callback);
      },
      close() { connection.readyState = 2; controller.abort(); },
    };
    fetchEventSource(address(path), {
      fetch: (_url, options) => request(path, options),
      signal: AbortSignal.any([scope.signal, controller.signal]),
      openWhenHidden: true,
      async onopen(response) {
        if (!response.ok || !response.headers.get('content-type')?.includes('text/event-stream')) {
          connection.readyState = 2;
          throw new Error(`Progress stream rejected: ${response.status}`);
        }
        connection.readyState = 1;
      },
      onmessage(message) {
        for (const callback of listeners.get(message.event || 'message') ?? []) {
          callback({ data: message.data, lastEventId: message.id });
        }
      },
      onclose() {
        if (!controller.signal.aborted) {
          connection.readyState = 2;
          connection.onerror?.(new Error('Progress stream closed before a terminal event.'));
        }
      },
      onerror(error) {
        if (controller.signal.aborted || scope.signal.aborted) throw error;
        connection.onerror?.(error);
        if (connection.readyState === 2) throw error;
        connection.readyState = 0;
      },
    }).catch(error => {
      if (!controller.signal.aborted && !scope.signal.aborted) connection.onerror?.(error);
    });
    return connection;
  }
  return { fetch: request, subscribe, CLOSED: 2, resourceUrl: path => resourceUrl(address(path)), dispose: () => {scope.abort(); scope = new AbortController();} };
}
