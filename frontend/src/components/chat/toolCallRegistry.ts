import type { Component } from 'vue';
import type { z } from 'zod';
import type { ToolCallPayload } from 'src/utils/model';
import AskQuestionToolCall from './AskQuestionToolCall.vue';
import ExpertAnswerToolCall from './ExpertAnswerToolCall.vue';
import GenericToolCall from './GenericToolCall.vue';
import GetAnalysisToolCall from './GetAnalysisToolCall.vue';
import HumanitarianContextToolCall from './HumanitarianContextToolCall.vue';
import ListAnalysesToolCall from './ListAnalysesToolCall.vue';
import NaturalEventsToolCall from './NaturalEventsToolCall.vue';
import RecallEventsToolCall from './RecallEventsToolCall.vue';
import RecordEventToolCall from './RecordEventToolCall.vue';
import SaveWhyStepToolCall from './SaveWhyStepToolCall.vue';
import SaniHubDocumentContentToolCall from './SaniHubDocumentContentToolCall.vue';
import SaniHubKnowledgeSearchToolCall from './SaniHubKnowledgeSearchToolCall.vue';
import SetRootCauseToolCall from './SetRootCauseToolCall.vue';
import Start5WhysAnalysisToolCall from './Start5WhysAnalysisToolCall.vue';
import WhoPublicationContentToolCall from './WhoPublicationContentToolCall.vue';
import WhoPublicationSearchToolCall from './WhoPublicationSearchToolCall.vue';
import {
    askQuestionToolCallPayloadSchema,
    baseToolCallPayloadSchema,
    expertAnswerToolCallPayloadSchema,
    getAnalysisToolCallPayloadSchema,
    humanitarianContextToolCallPayloadSchema,
    listAnalysesToolCallPayloadSchema,
    naturalEventsToolCallPayloadSchema,
    recallEventsToolCallPayloadSchema,
    recordEventToolCallPayloadSchema,
    saveWhyStepToolCallPayloadSchema,
    sanihubDocumentContentToolCallPayloadSchema,
    sanihubKnowledgeSearchToolCallPayloadSchema,
    setRootCauseToolCallPayloadSchema,
    start5WhysAnalysisToolCallPayloadSchema,
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
    ask_question: defineToolCall(AskQuestionToolCall, askQuestionToolCallPayloadSchema),
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
    get_analysis: defineToolCall(GetAnalysisToolCall, getAnalysisToolCallPayloadSchema),
    list_analyses: defineToolCall(ListAnalysesToolCall, listAnalysesToolCallPayloadSchema),
    record_event: defineToolCall(RecordEventToolCall, recordEventToolCallPayloadSchema),
    recall_events: defineToolCall(RecallEventsToolCall, recallEventsToolCallPayloadSchema),
    save_why_step: defineToolCall(SaveWhyStepToolCall, saveWhyStepToolCallPayloadSchema),
    set_root_cause: defineToolCall(SetRootCauseToolCall, setRootCauseToolCallPayloadSchema),
    start_5_whys_analysis: defineToolCall(
        Start5WhysAnalysisToolCall,
        start5WhysAnalysisToolCallPayloadSchema,
    ),
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
        return { component: GenericToolCall, payload: null };
    }

    const registration = TOOL_CALL_REGISTRY[basePayload.data.tool_name];
    if (!registration) {
        return { component: GenericToolCall, payload: basePayload.data };
    }

    const parsedPayload = registration.inputSchema.safeParse(payload);
    if (!parsedPayload.success) {
        return { component: GenericToolCall, payload: basePayload.data };
    }

    return { component: registration.component, payload: parsedPayload.data };
}
