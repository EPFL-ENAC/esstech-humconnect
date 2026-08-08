import type { Component } from 'vue';
import type { z } from 'zod';
import type { ToolCallPayload } from 'src/utils/model';
import ExpertAnswerToolCall from './ExpertAnswerToolCall.vue';
import GenericToolCall from './GenericToolCall.vue';
import HumanitarianContextToolCall from './HumanitarianContextToolCall.vue';
import NaturalEventsToolCall from './NaturalEventsToolCall.vue';
import RecallEventsToolCall from './RecallEventsToolCall.vue';
import RecordEventToolCall from './RecordEventToolCall.vue';
import SaniHubDocumentContentToolCall from './SaniHubDocumentContentToolCall.vue';
import SaniHubKnowledgeSearchToolCall from './SaniHubKnowledgeSearchToolCall.vue';
import WhoPublicationContentToolCall from './WhoPublicationContentToolCall.vue';
import WhoPublicationSearchToolCall from './WhoPublicationSearchToolCall.vue';
import {
    baseToolCallPayloadSchema,
    expertAnswerToolCallPayloadSchema,
    humanitarianContextToolCallPayloadSchema,
    naturalEventsToolCallPayloadSchema,
    recallEventsToolCallPayloadSchema,
    recordEventToolCallPayloadSchema,
    sanihubDocumentContentToolCallPayloadSchema,
    sanihubKnowledgeSearchToolCallPayloadSchema,
    whoPublicationContentToolCallPayloadSchema,
    whoPublicationSearchToolCallPayloadSchema,
} from './toolCallSchemas';

interface ToolCallRegistration {
    component: Component;
    inputSchema: z.ZodType;
}

interface ResolvedToolCall {
    component: Component;
    payload: unknown;
}

function defineToolCall<Schema extends z.ZodType>(
    component: Component<{ payload: z.output<Schema> }>,
    inputSchema: Schema,
): ToolCallRegistration {
    return { component, inputSchema };
}

const TOOL_CALL_REGISTRY: Record<string, ToolCallRegistration> = {
    ask_meditron: defineToolCall(ExpertAnswerToolCall, expertAnswerToolCallPayloadSchema),
    ask_legitron: defineToolCall(ExpertAnswerToolCall, expertAnswerToolCallPayloadSchema),
    get_humanitarian_context: defineToolCall(
        HumanitarianContextToolCall,
        humanitarianContextToolCallPayloadSchema,
    ),
    get_natural_events_context: defineToolCall(
        NaturalEventsToolCall,
        naturalEventsToolCallPayloadSchema,
    ),
    search_who_publications: defineToolCall(
        WhoPublicationSearchToolCall,
        whoPublicationSearchToolCallPayloadSchema,
    ),
    get_who_publication_content: defineToolCall(
        WhoPublicationContentToolCall,
        whoPublicationContentToolCallPayloadSchema,
    ),
    record_event: defineToolCall(RecordEventToolCall, recordEventToolCallPayloadSchema),
    recall_events: defineToolCall(RecallEventsToolCall, recallEventsToolCallPayloadSchema),
    sanihub_knowledgeSearch: defineToolCall(
        SaniHubKnowledgeSearchToolCall,
        sanihubKnowledgeSearchToolCallPayloadSchema,
    ),
    sanihub_getDocumentContent: defineToolCall(
        SaniHubDocumentContentToolCall,
        sanihubDocumentContentToolCallPayloadSchema,
    ),
};

export function resolveToolCall(payload: ToolCallPayload | null): ResolvedToolCall {
    const basePayload = baseToolCallPayloadSchema.safeParse(payload);
    if (!basePayload.success) {
        console.log('Failed to parse base tool call payload:', basePayload.error);
        return { component: GenericToolCall, payload: null };
    }

    const registration = TOOL_CALL_REGISTRY[basePayload.data.tool_name];
    console.log('Resolved tool call:', {
        tool_name: basePayload.data.tool_name,
        registration: registration ? 'found' : 'not found',
    });
    if (!registration) {
        return { component: GenericToolCall, payload: basePayload.data };
    }

    const parsedPayload = registration.inputSchema.safeParse(payload);
    if (!parsedPayload.success) {
        console.log(parsedPayload.error);
        return { component: GenericToolCall, payload: basePayload.data };
    }

    return { component: registration.component, payload: parsedPayload.data };
}
