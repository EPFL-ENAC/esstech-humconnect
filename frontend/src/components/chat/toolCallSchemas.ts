import { z } from 'zod';
import {
    eventContinents,
    eventTags,
    professionCategories,
    type ToolCallPayload,
} from 'src/utils/model';

const toolCallStatusSchema = z.enum(['running', 'finished', 'failed']);

export const baseToolCallPayloadSchema = z.object({
    tool_name: z.string(),
    tool_label: z.string(),
    call_id: z.string(),
    arguments: z.record(z.string(), z.unknown()).nullable(),
    status: toolCallStatusSchema,
    answer: z.string().nullable(),
    error: z.string().nullable(),
}) satisfies z.ZodType<ToolCallPayload>;

const eventTagSchema = z.enum(eventTags);
const eventContinentSchema = z.enum(eventContinents);
const professionCategorySchema = z.enum(professionCategories);

const eventCoordinatesSchema = z.looseObject({
    latitude: z.number().min(-90).max(90),
    longitude: z.number().min(-180).max(180),
});

const eventLocationSchema = z.looseObject({
    raw_text: z.string().nullable(),
    continent: eventContinentSchema.nullable(),
    country_code: z
        .string()
        .regex(/^[A-Z]{2}$/)
        .nullable(),
    region: z.string().nullable(),
    city: z.string().nullable(),
    address: z.string().nullable(),
    place_name: z.string().nullable(),
    detail: z.string().nullable(),
    coordinates: eventCoordinatesSchema.nullable(),
});

const recordedEventSchema = z.looseObject({
    id: z.string(),
    chat_id: z.string(),
    initiated_by_user_id: z.string(),
    source_message_id: z.string(),
    original_text: z.string(),
    event_name: z.string(),
    event_datetime: z.string().nullable(),
    event_date_granularity: z.string(),
    event_date_precision: z.string(),
    event_date_input: z.record(z.string(), z.unknown()),
    event_end_datetime: z.string().nullable(),
    event_end_date_granularity: z.string().nullable(),
    event_end_date_precision: z.string().nullable(),
    event_end_date_input: z.record(z.string(), z.unknown()).nullable(),
    event_location: eventLocationSchema,
    tags: z.array(eventTagSchema),
    keywords: z.array(z.string()),
    affected_profession_categories: z.array(professionCategorySchema),
    response_profession_categories: z.array(professionCategorySchema),
    local_severity: z.number().min(0).max(10).nullable(),
    country_severity: z.number().min(0).max(10).nullable(),
    global_severity: z.number().min(0).max(10).nullable(),
    created_at: z.string(),
});

const recordEventResultSchema = z.looseObject({
    message: z.string(),
    event: recordedEventSchema,
});

const recallEventsResultSchema = z.looseObject({
    message: z.string(),
    events: z.array(recordedEventSchema),
});

const humanitarianContextFiltersSchema = z.looseObject({
    provider: z.string(),
    country: z.string(),
    created_from: z.string(),
    limit_per_endpoint: z.number().int(),
    sort: z.array(z.string()),
    report_query: z.string(),
    disaster_status: z.string(),
});

const humanitarianContextItemSchema = z.looseObject({
    provider: z.string(),
    type: z.enum(['report', 'disaster']),
    id: z.string(),
    title: z.string(),
    category: z.string(),
    time: z.string().nullable().optional().default(null),
    source_url: z.string().nullable().optional().default(null),
    sources: z.array(z.string()),
    country: z.string(),
    location_precision: z.literal('country'),
});

const humanitarianContextResultSchema = z.looseObject({
    summary: z.looseObject({
        message: z.string(),
        counts: z.record(z.string(), z.number().int()),
    }),
    country: z.string(),
    filters: humanitarianContextFiltersSchema,
    items: z.array(humanitarianContextItemSchema),
    warnings: z.array(z.string()).optional(),
});

function jsonString<Schema extends z.ZodType>(schema: Schema) {
    return z
        .string()
        .transform((raw, context): unknown => {
            try {
                return JSON.parse(raw) as unknown;
            } catch {
                context.addIssue({ code: 'custom', message: 'Expected a JSON-encoded value' });
                return z.NEVER;
            }
        })
        .pipe(schema);
}

function valueOrJsonString<Schema extends z.ZodType>(schema: Schema) {
    return z.union([schema, jsonString(schema)]);
}

type ToolCallWithAnswer = {
    status: z.output<typeof toolCallStatusSchema>;
    answer: unknown;
};

function requireFinishedAnswer<Output extends ToolCallWithAnswer, Input>(
    schema: z.ZodType<Output, Input>,
) {
    return schema.refine((payload) => payload.status !== 'finished' || payload.answer !== null, {
        message: 'Finished tool calls must contain an answer',
        path: ['answer'],
    });
}

const expertArgumentsSchema = z.strictObject({
    prompt: z.string().trim().min(1),
    system_prompt: z.string().optional(),
});

function expertToolCallPayloadSchema<const ToolName extends 'ask_meditron' | 'ask_legitron'>(
    toolName: ToolName,
) {
    return requireFinishedAnswer(
        baseToolCallPayloadSchema.extend({
            tool_name: z.literal(toolName),
            arguments: expertArgumentsSchema,
        }),
    );
}

export const askMeditronToolCallPayloadSchema = expertToolCallPayloadSchema('ask_meditron');
export const askLegitronToolCallPayloadSchema = expertToolCallPayloadSchema('ask_legitron');
export const expertAnswerToolCallPayloadSchema = z.union([
    askMeditronToolCallPayloadSchema,
    askLegitronToolCallPayloadSchema,
]);

export type ExpertAnswerToolCallPayload = z.output<typeof expertAnswerToolCallPayloadSchema>;

export const humanitarianContextToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('get_humanitarian_context'),
        arguments: z.strictObject({ country_name: z.string().trim().min(1) }),
        answer: jsonString(humanitarianContextResultSchema).nullable(),
    }),
);

export type HumanitarianContextToolCallPayload = z.output<
    typeof humanitarianContextToolCallPayloadSchema
>;
export type HumanitarianContextItem = z.output<typeof humanitarianContextItemSchema>;

const recordEventDateSchema = z.record(z.string(), z.unknown());
const recordEventSeveritySchema = z.strictObject({
    local: z.number().min(0).max(10),
    country: z.number().min(0).max(10),
    global: z.number().min(0).max(10),
});

const recordEventArgumentsSchema = z.strictObject({
    original_text: z.string().trim().min(1),
    event_name: z.string().trim().min(1),
    event_date: valueOrJsonString(recordEventDateSchema),
    event_end_date: valueOrJsonString(recordEventDateSchema.nullable()),
    event_location: valueOrJsonString(eventLocationSchema),
    tags: valueOrJsonString(z.array(eventTagSchema).min(1)),
    keywords: valueOrJsonString(z.array(z.string().trim().min(1))),
    affected_profession_categories: valueOrJsonString(z.array(professionCategorySchema)),
    response_profession_categories: valueOrJsonString(z.array(professionCategorySchema)),
    severity: valueOrJsonString(recordEventSeveritySchema),
});

export const recordEventToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('record_event'),
        arguments: recordEventArgumentsSchema,
        answer: jsonString(recordEventResultSchema).nullable(),
    }),
);

export type RecordEventToolCallPayload = z.output<typeof recordEventToolCallPayloadSchema>;

const recallEventTagsSchema = valueOrJsonString(z.array(eventTagSchema));
const recallEventsArgumentsSchema = z.strictObject({
    keyword: z.string().trim().min(1).nullable().optional().default(null),
    date_start: z.string().nullable().optional().default(null),
    date_end: z.string().nullable().optional().default(null),
    tags: recallEventTagsSchema.optional().default([]),
    tag_match: z.enum(['all', 'any']).optional().default('all'),
    limit: z.number().int().min(1).max(50).optional().default(10),
});

export const recallEventsToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('recall_events'),
        arguments: recallEventsArgumentsSchema,
        answer: jsonString(recallEventsResultSchema).nullable(),
    }),
);

export type RecallEventsToolCallPayload = z.output<typeof recallEventsToolCallPayloadSchema>;

export type ToolCallDisplayPayload = Omit<ToolCallPayload, 'arguments' | 'answer'> & {
    arguments: unknown;
    answer: unknown;
};
