export interface ColorStop {
    progress: number;
    color: string;
}

interface RgbaColor {
    red: number;
    green: number;
    blue: number;
    alpha: number;
}

const hexColorPattern = /^#(?:[\da-f]{3,4}|[\da-f]{6}|[\da-f]{8})$/i;

export class ColorScale {
    readonly stops: readonly ColorStop[];

    constructor(stops: readonly ColorStop[]) {
        if (!stops.length) {
            throw new TypeError('ColorScale requires at least one stop.');
        }

        const sortedStops = stops
            .map((stop) => {
                validateProgress(stop.progress, 'Color stop progress');
                const color = formatHexColor(parseHexColor(stop.color));
                return Object.freeze({ progress: stop.progress, color });
            })
            .sort((first, second) => first.progress - second.progress);

        for (let index = 1; index < sortedStops.length; index += 1) {
            if (sortedStops[index]?.progress === sortedStops[index - 1]?.progress) {
                throw new TypeError('ColorScale stop progress values must be unique.');
            }
        }

        this.stops = Object.freeze(sortedStops);
        Object.freeze(this);
    }

    sample(progress: number): string {
        validateProgress(progress, 'Color sample progress');

        const firstStop = this.stops[0];
        const lastStop = this.stops[this.stops.length - 1];
        if (!firstStop || !lastStop) {
            throw new TypeError('ColorScale requires at least one stop.');
        }
        if (progress <= firstStop.progress) {
            return formatHexColor(parseHexColor(firstStop.color));
        }
        if (progress >= lastStop.progress) {
            return formatHexColor(parseHexColor(lastStop.color));
        }

        const upperIndex = this.stops.findIndex((stop) => stop.progress >= progress);
        const lowerStop = this.stops[upperIndex - 1];
        const upperStop = this.stops[upperIndex];
        if (!lowerStop || !upperStop) {
            throw new TypeError('ColorScale could not resolve the requested progress.');
        }

        const localProgress =
            (progress - lowerStop.progress) / (upperStop.progress - lowerStop.progress);
        const lowerColor = parseHexColor(lowerStop.color);
        const upperColor = parseHexColor(upperStop.color);

        return formatHexColor({
            red: interpolateChannel(lowerColor.red, upperColor.red, localProgress),
            green: interpolateChannel(lowerColor.green, upperColor.green, localProgress),
            blue: interpolateChannel(lowerColor.blue, upperColor.blue, localProgress),
            alpha: interpolateChannel(lowerColor.alpha, upperColor.alpha, localProgress),
        });
    }

    toLinearGradient(deg: number = 90): string {
        const gradientStops = this.stops.map((stop) => `${stop.color} ${stop.progress * 100}%`);
        return `linear-gradient(${deg}deg, ${gradientStops.join(', ')})`;
    }
}

function validateProgress(progress: number, label: string): void {
    if (!Number.isFinite(progress) || progress < 0 || progress > 1) {
        throw new RangeError(`${label} must be a finite number between 0 and 1.`);
    }
}

function parseHexColor(color: string): RgbaColor {
    if (!hexColorPattern.test(color)) {
        throw new TypeError(`Invalid hexadecimal color: ${color}`);
    }

    const compact = color.slice(1);
    const expanded =
        compact.length <= 4
            ? [...compact].map((character) => `${character}${character}`).join('')
            : compact;
    const withAlpha = expanded.length === 6 ? `${expanded}ff` : expanded;

    return {
        red: Number.parseInt(withAlpha.slice(0, 2), 16),
        green: Number.parseInt(withAlpha.slice(2, 4), 16),
        blue: Number.parseInt(withAlpha.slice(4, 6), 16),
        alpha: Number.parseInt(withAlpha.slice(6, 8), 16),
    };
}

function formatHexColor(color: RgbaColor): string {
    const rgb = `${formatChannel(color.red)}${formatChannel(color.green)}${formatChannel(color.blue)}`;
    const alpha = color.alpha === 255 ? '' : formatChannel(color.alpha);
    return `#${rgb}${alpha}`;
}

function formatChannel(channel: number): string {
    return channel.toString(16).padStart(2, '0');
}

function interpolateChannel(start: number, end: number, progress: number): number {
    return Math.round(start + (end - start) * progress);
}
