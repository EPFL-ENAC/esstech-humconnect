import { onBeforeUnmount, ref, toValue, watch, type MaybeRefOrGetter } from 'vue';
import { useAuthStore } from 'src/stores/auth';

interface ApiEventStreamOptions<T> {
    url: MaybeRefOrGetter<string>;
    onEvent: (event: T) => void;
    onError?: (error: Error | null) => void;
    reconnectDelayMs?: number;
}

export function useApiEventStream<T>({
    url,
    onEvent,
    onError,
    reconnectDelayMs = 1000,
}: ApiEventStreamOptions<T>) {
    const authStore = useAuthStore();
    const connected = ref(false);
    const error = ref<Error | null>(null);

    let controller: AbortController | null = null;
    let reconnectTimer: number | undefined;
    let reconnectEnabled = true;
    let generation = 0;

    async function connect() {
        const currentUrl = toValue(url);
        if (!currentUrl) {
            stop();
            return;
        }

        generation += 1;
        const currentGeneration = generation;

        clearReconnectTimer();
        controller?.abort();

        const currentController = new AbortController();
        controller = currentController;
        connected.value = false;

        try {
            const response = await authStore.fetchApi(currentUrl, {
                headers: {
                    Accept: 'text/event-stream',
                },
                signal: currentController.signal,
            });

            if (controller !== currentController || generation !== currentGeneration) {
                await response.body?.cancel();
                return;
            }

            if (response.status === 401) {
                reconnectEnabled = false;
            }

            if (!response.ok || !response.body) {
                throw new Error(`Event stream failed with status ${response.status}`);
            }

            connected.value = true;
            setError(null);

            await readSseFrames(response.body, (event: T) => {
                if (controller !== currentController || generation !== currentGeneration) {
                    return;
                }

                onEvent(event);
            });
        } catch (err) {
            if (!currentController.signal.aborted) {
                setError(err instanceof Error ? err : new Error('Event stream failed'));
            }
        } finally {
            if (controller === currentController && generation === currentGeneration) {
                connected.value = false;
                controller = null;

                if (reconnectEnabled) {
                    reconnectTimer = window.setTimeout(() => {
                        void connect();
                    }, reconnectDelayMs);
                }
            }
        }
    }

    function restart() {
        reconnectEnabled = true;
        void connect();
    }

    function stop() {
        reconnectEnabled = false;
        generation += 1;
        clearReconnectTimer();

        const currentController = controller;
        controller = null;
        currentController?.abort();
        connected.value = false;
    }

    function clearReconnectTimer() {
        if (reconnectTimer !== undefined) {
            window.clearTimeout(reconnectTimer);
            reconnectTimer = undefined;
        }
    }

    function setError(currentError: Error | null) {
        error.value = currentError;
        onError?.(currentError);
    }

    watch(
        () => toValue(url),
        () => restart(),
        { immediate: true },
    );

    onBeforeUnmount(stop);

    return {
        connected,
        error,
        restart,
        stop,
    };
}

async function readSseFrames<T>(body: ReadableStream<Uint8Array>, onEvent: (event: T) => void) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            break;
        }

        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split(/\r?\n\r?\n/);
        buffer = frames.pop() ?? '';

        for (const frame of frames) {
            const data = frame
                .split(/\r?\n/)
                .filter((line) => line.startsWith('data:'))
                .map((line) => line.slice(5).trimStart())
                .join('\n');

            if (data) {
                onEvent(JSON.parse(data) as T);
            }
        }
    }
}
