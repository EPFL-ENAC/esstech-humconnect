import type { Component } from 'vue';
import ExpertAnswerToolCall from './ExpertAnswerToolCall.vue';
import GenericToolCall from './GenericToolCall.vue';
import HumanitarianContextToolCall from './HumanitarianContextToolCall.vue';

const TOOL_CALL_COMPONENTS: Record<string, Component> = {
    ask_meditron: ExpertAnswerToolCall,
    ask_legitron: ExpertAnswerToolCall,
    get_humanitarian_context: HumanitarianContextToolCall,
};

export function resolveToolCallComponent(toolName?: string): Component {
    return toolName ? (TOOL_CALL_COMPONENTS[toolName] ?? GenericToolCall) : GenericToolCall;
}
