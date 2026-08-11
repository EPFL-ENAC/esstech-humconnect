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

function jsonStringWithOptionalTrailer<Schema extends z.ZodType>(schema: Schema) {
    return z
        .string()
        .transform((raw, context): unknown => {
            const json = raw.split(/\n\s*---\s*\n/, 1)[0]?.trim() ?? '';

            try {
                return JSON.parse(json) as unknown;
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

const hungerMapPhaseEstimateSchema = z.looseObject({
    percentage: z.number().min(0).max(100),
    population: z.number().int().nonnegative(),
});

const hungerMapCountryEstimateSchema = z.looseObject({
    country_code: z.string().regex(/^[A-Z]{2}$/),
    wfp_area_code: z.string().regex(/^[A-Z]{3}$/),
    name: z.string(),
    reference_period: z.string(),
    analysis_date: z.string(),
    data_source: z.string(),
    phase_3_or_above: hungerMapPhaseEstimateSchema,
    phase_4_or_above: hungerMapPhaseEstimateSchema,
    phase_5: hungerMapPhaseEstimateSchema,
});

const hungerMapGlobalHeadlineSchema = z.looseObject({
    period: z.string(),
    acute_food_insecurity_millions: z.number().nonnegative(),
    covered_country_count: z.number().int().nonnegative(),
    source_note: z.string(),
});

const hungerMapResponseSchema = z.looseObject({
    provider: z.literal('WFP HungerMap LIVE'),
    scope: z.enum(['country', 'global']),
    headline: hungerMapGlobalHeadlineSchema.nullable().optional(),
    available_country_estimate_count: z.number().int().nonnegative(),
    countries: z.array(hungerMapCountryEstimateSchema),
    source_url: z.string(),
    warnings: z.array(z.string()),
});

export const hungerMapToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('get_hunger_map_context'),
        arguments: z.strictObject({
            country: z.string().regex(/^(global|[A-Z]{2,3})$/),
        }),
        answer: jsonString(hungerMapResponseSchema).nullable(),
    }),
);

export type HungerMapToolCallPayload = z.output<typeof hungerMapToolCallPayloadSchema>;
export type HungerMapResponse = z.output<typeof hungerMapResponseSchema>;
export type HungerMapGlobalHeadline = z.output<typeof hungerMapGlobalHeadlineSchema>;
export type HungerMapCountryEstimate = z.output<typeof hungerMapCountryEstimateSchema>;
export type HungerMapPhaseEstimate = z.output<typeof hungerMapPhaseEstimateSchema>;

const naturalEventsArgumentsSchema = z.strictObject({
    center_latitude: z.number().min(-90).max(90),
    center_longitude: z.number().min(-180).max(180),
    radius_km: z.number().positive().max(1000),
});

const naturalEventSchema = z.looseObject({
    provider: z.enum(['NASA EONET', 'USGS Earthquake Catalog']),
    id: z.string(),
    title: z.string(),
    category: z.string().nullable().optional().default(null),
    time: z.string().nullable().optional().default(null),
    status: z.string(),
    latitude: z.number().min(-90).max(90),
    longitude: z.number().min(-180).max(180),
    distance_km: z.number().nonnegative(),
    magnitude: z.number().nullable().optional().default(null),
    source_url: z.string().nullable().optional().default(null),
});

const naturalEventsResultSchema = z.looseObject({
    summary: z.looseObject({
        message: z.string(),
        counts: z.looseObject({
            nasa_eonet: z.number().int().nonnegative(),
            usgs_earthquakes: z.number().int().nonnegative(),
        }),
    }),
    center: z.looseObject({
        latitude: z.number().min(-90).max(90),
        longitude: z.number().min(-180).max(180),
        radius_km: z.number().positive().max(1000),
    }),
    events: z.array(naturalEventSchema),
    warnings: z.array(z.string()).nullable().optional().default(null),
});

export const naturalEventsToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('get_natural_events_context'),
        arguments: naturalEventsArgumentsSchema,
        answer: jsonString(naturalEventsResultSchema).nullable(),
    }),
);

export type NaturalEventsToolCallPayload = z.output<typeof naturalEventsToolCallPayloadSchema>;
export type NaturalEvent = z.output<typeof naturalEventSchema>;

const whoPublicationSchema = z.looseObject({
    item_id: z.string().uuid(),
    title: z.string(),
    abstract: z.string().nullable(),
    authors: z.array(z.string()),
    published_date: z.string().nullable(),
    languages: z.array(z.string()),
    subjects: z.array(z.string()),
    document_types: z.array(z.string()),
    source_url: z.string(),
});

const whoPublicationSearchResultSchema = z.looseObject({
    query: z.string(),
    total: z.number().int().nonnegative(),
    results: z.array(whoPublicationSchema),
});

const whoPublicationDocumentSchema = z.looseObject({
    filename: z.string(),
    content: z.string(),
    truncated: z.boolean(),
});

const whoPublicationContentResultSchema = z.looseObject({
    item_id: z.string().uuid(),
    title: z.string(),
    source_url: z.string(),
    documents: z.array(whoPublicationDocumentSchema),
    warnings: z.array(z.string()),
});

export const whoPublicationSearchToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('search_who_publications'),
        arguments: z.strictObject({
            query: z.string().trim().min(1),
            limit: z.number().int().min(1).max(10).optional().default(5),
        }),
        answer: jsonString(whoPublicationSearchResultSchema).nullable(),
    }),
);

export const whoPublicationContentToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('get_who_publication_content'),
        arguments: z.strictObject({ item_id: z.string().uuid() }),
        answer: jsonString(whoPublicationContentResultSchema).nullable(),
    }),
);

export type WhoPublicationSearchToolCallPayload = z.output<
    typeof whoPublicationSearchToolCallPayloadSchema
>;
export type WhoPublicationContentToolCallPayload = z.output<
    typeof whoPublicationContentToolCallPayloadSchema
>;
export type WhoPublication = z.output<typeof whoPublicationSchema>;

const sanihubTopicSchema = z.enum([
    'Preparedness',
    'Needs Assessment',
    'Strategic Planning',
    'Resource Mobilisation',
    'Implementation Monitoring',
    'Review Evaluation',
    'Sanitation Technologies',
    'Technology Selection',
    'Faecal Sludge',
    'Sanitation Software',
    'Wider Systems',
    'Cross-Cutting Issues',
    'Coordination Sectors',
    'Accountability',
    'Capacity Development',
    'Research Innovation',
    'Knowledge Management',
    'Case Studies',
    'Challenging Contexts',
    'Disaster Scenarios',
    'Climate Challenges',
    'Ground Conditions',
]);

const sanihubKnowledgeSearchArgumentsSchema = z.strictObject({
    tenant: z.literal('sanihub').optional().default('sanihub'),
    queries: z.array(z.string().trim().min(1)).min(1).max(6),
    userQuery: z.string().trim().min(1),
    documentListOnly: z.boolean().optional().default(false),
    segments: z.array(z.string().trim().min(1)).max(4).optional().default([]),
    topics: z.array(sanihubTopicSchema).max(5).optional().default([]),
    locations: z
        .array(z.string().regex(/^[A-Z]{2}$/))
        .max(10)
        .optional()
        .default([]),
});

const sanihubKnowledgeResultSchema = z.looseObject({
    REF_ID: z.string(),
    url: z.string().startsWith('http'),
    title: z.string(),
    documentId: z.string(),
    pageNum: z.number().int().positive().optional(),
    content: z.string(),
    score: z.number(),
    source: z.string(),
    documentListOnly: z.boolean().optional(),
    rerank_score: z.number().optional(),
});

const sanihubKnowledgeSearchResultSchema = z.looseObject({
    message: z.string(),
    queries: z.array(z.string()),
    query: z.string(),
    resultCount: z.number().int().nonnegative(),
    results: z.array(sanihubKnowledgeResultSchema),
});

const sanihubDocumentPagesSchema = z
    .string()
    .trim()
    .regex(/^\d+(?:\s*,\s*\d+){0,19}$/);

const sanihubDocumentContentResultSchema = z.looseObject({
    documentId: z.string(),
    title: z.string(),
    totalPages: z.number().int().nonnegative(),
    pages: z.array(
        z.looseObject({
            pageNum: z.number().int().positive(),
            content: z.string(),
        }),
    ),
    message: z.string(),
});

export const sanihubKnowledgeSearchToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('sanihub_knowledgeSearch'),
        arguments: sanihubKnowledgeSearchArgumentsSchema,
        answer: jsonStringWithOptionalTrailer(sanihubKnowledgeSearchResultSchema).nullable(),
    }),
);

export const sanihubDocumentContentToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('sanihub_getDocumentContent'),
        arguments: z.strictObject({
            documentId: z.string().trim().min(1),
            pages: sanihubDocumentPagesSchema,
        }),
        answer: jsonStringWithOptionalTrailer(sanihubDocumentContentResultSchema).nullable(),
    }),
);

export type SaniHubKnowledgeSearchToolCallPayload = z.output<
    typeof sanihubKnowledgeSearchToolCallPayloadSchema
>;
export type SaniHubDocumentContentToolCallPayload = z.output<
    typeof sanihubDocumentContentToolCallPayloadSchema
>;
export type SaniHubKnowledgeResult = z.output<typeof sanihubKnowledgeResultSchema>;

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

const ROOT_CAUSE_ANALYSIS_MAX_WHYS = 5;
const analysisStatusSchema = z.enum(['in_progress', 'completed']);
const analysisNextExpectedSchema = z.enum([
    'why_step',
    'why_step_or_root_cause',
    'root_cause',
    'none',
]);

const whyQuestionAnswerSchema = z.looseObject({
    level: z.number().int().min(1).max(ROOT_CAUSE_ANALYSIS_MAX_WHYS),
    question: z.string(),
    answer: z.string().nullable(),
});

export type WhyQuestionAnswer = z.output<typeof whyQuestionAnswerSchema>;

const rootCauseAnalysisSnapshotSchema = z.looseObject({
    analysis_id: z.string(),
    problem_statement: z.string(),
    status: analysisStatusSchema,
    current_level: z.number().int().min(0).max(ROOT_CAUSE_ANALYSIS_MAX_WHYS),
    next_expected: analysisNextExpectedSchema,
    can_save_why_step: z.boolean(),
    can_set_root_cause: z.boolean(),
    questions_and_answers: z.array(whyQuestionAnswerSchema),
    root_cause: z.string().nullable(),
    created_at: z.string(),
    updated_at: z.string(),
});

export type RootCauseAnalysisSnapshot = z.output<typeof rootCauseAnalysisSnapshotSchema>;

const rootCauseAnalysisSnapshotResultSchema = z.looseObject({
    message: z.string(),
    analysis: rootCauseAnalysisSnapshotSchema,
});

const analysisSummarySchema = z.looseObject({
    analysis_id: z.string(),
    problem_statement: z.string(),
    status: analysisStatusSchema,
    current_level: z.number().int().min(0).max(ROOT_CAUSE_ANALYSIS_MAX_WHYS),
    created_at: z.string(),
});

export type RootCauseAnalysisSummary = z.output<typeof analysisSummarySchema>;

const listAnalysesResultSchema = z.looseObject({
    message: z.string(),
    analyses: z.array(analysisSummarySchema),
});

export const start5WhysAnalysisToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('start_5_whys_analysis'),
        arguments: z.strictObject({
            problem_statement: z.string().trim().min(1),
        }),
        answer: jsonString(rootCauseAnalysisSnapshotResultSchema).nullable(),
    }),
);

export type Start5WhysAnalysisToolCallPayload = z.output<
    typeof start5WhysAnalysisToolCallPayloadSchema
>;

export const saveWhyStepToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('save_why_step'),
        arguments: z.strictObject({
            analysis_id: z.string().trim().min(1),
            question: z.string().trim().min(1),
            answer: z.string().trim().min(1),
        }),
        answer: jsonString(rootCauseAnalysisSnapshotResultSchema).nullable(),
    }),
);

export type SaveWhyStepToolCallPayload = z.output<typeof saveWhyStepToolCallPayloadSchema>;

export const getAnalysisToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('get_analysis'),
        arguments: z.strictObject({
            analysis_id: z.string().trim().min(1),
        }),
        answer: jsonString(rootCauseAnalysisSnapshotResultSchema).nullable(),
    }),
);

export type GetAnalysisToolCallPayload = z.output<typeof getAnalysisToolCallPayloadSchema>;

export const setRootCauseToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('set_root_cause'),
        arguments: z.strictObject({
            analysis_id: z.string().trim().min(1),
            root_cause: z.string().trim().min(1),
        }),
        answer: jsonString(rootCauseAnalysisSnapshotResultSchema).nullable(),
    }),
);

export type SetRootCauseToolCallPayload = z.output<typeof setRootCauseToolCallPayloadSchema>;

export const listAnalysesToolCallPayloadSchema = requireFinishedAnswer(
    baseToolCallPayloadSchema.extend({
        tool_name: z.literal('list_analyses'),
        arguments: z.strictObject({
            status: analysisStatusSchema.nullable().optional().default(null),
        }),
        answer: jsonString(listAnalysesResultSchema).nullable(),
    }),
);

export type ListAnalysesToolCallPayload = z.output<typeof listAnalysesToolCallPayloadSchema>;

const askQuestionArgumentsSchema = z.strictObject({
    question: z.string().trim().min(1),
    possible_answers: z.array(z.string().trim().min(1)),
});

export const askQuestionToolCallPayloadSchema = baseToolCallPayloadSchema.extend({
    tool_name: z.literal('ask_question'),
    arguments: askQuestionArgumentsSchema,
});

export type AskQuestionToolCallPayload = z.output<typeof askQuestionToolCallPayloadSchema>;

export type ToolCallDisplayPayload = Omit<ToolCallPayload, 'arguments' | 'answer'> & {
    arguments: unknown;
    answer: unknown;
};
