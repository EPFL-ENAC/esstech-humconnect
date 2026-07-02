import { onBeforeUnmount } from 'vue';

export function useDebouncedAction<TArgs extends unknown[], TResult>(
    action: (...args: TArgs) => TResult,
    delayMs: number,
) {
    let timeout: number | undefined;
    let latestArgs: TArgs | null = null;

    function cancel() {
        if (timeout !== undefined) {
            window.clearTimeout(timeout);
            timeout = undefined;
        }
        latestArgs = null;
    }

    function run(...args: TArgs) {
        latestArgs = args;

        if (timeout !== undefined) {
            window.clearTimeout(timeout);
        }

        timeout = window.setTimeout(() => {
            const argsToRun = latestArgs;
            timeout = undefined;
            latestArgs = null;

            if (argsToRun !== null) {
                void action(...argsToRun);
            }
        }, delayMs);
    }

    function runImmediately(...args: TArgs): TResult {
        cancel();
        return action(...args);
    }

    onBeforeUnmount(cancel);

    return {
        cancel,
        run,
        runImmediately,
    };
}
