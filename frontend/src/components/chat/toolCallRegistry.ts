import type { Component } from 'vue';
import GenericToolCall from './GenericToolCall.vue';
import HumanitarianContextToolCall from './HumanitarianContextToolCall.vue';

const TOOL_CALL_COMPONENTS: Record<string, Component> = {
    get_humanitarian_context: HumanitarianContextToolCall,
};

export function resolveToolCallComponent(toolName?: string): Component {
    return toolName ? (TOOL_CALL_COMPONENTS[toolName] ?? GenericToolCall) : GenericToolCall;
}
