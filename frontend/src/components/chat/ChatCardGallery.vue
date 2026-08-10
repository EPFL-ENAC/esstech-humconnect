<template>
    <div class="chat-card-gallery">
        <slot />
    </div>
</template>

<style scoped lang="scss">
.chat-card-gallery {
    display: grid;
    gap: 10px;
    grid-auto-columns: min(40ch, 82%);
    grid-auto-flow: column;
    overflow-x: auto;
    padding: 4px 4px 10px;
    scroll-padding-inline: 4px;
    scroll-snap-type: x proximity;
    scrollbar-width: thin;
}

.chat-card-gallery :slotted(*) {
    scroll-snap-align: start;
    scroll-margin-inline: 4px;
}

@media (max-width: 520px) {
    .chat-card-gallery {
        grid-auto-columns: 86%;
    }
}
</style>
