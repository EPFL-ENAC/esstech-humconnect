<template>
    <div class="chat-card-gallery">
        <slot />
    </div>
</template>

<style scoped lang="scss">
.chat-card-gallery {
    display: flex;
    gap: 10px;
    margin: 0 -2px;
    overflow-x: auto;
    padding: 2px 2px 10px;
    scroll-snap-type: x proximity;
    scrollbar-width: thin;
}

.chat-card-gallery :slotted(*) {
    flex: 0 0 min(250px, 82%);
    scroll-snap-align: start;
}

@media (max-width: 520px) {
    .chat-card-gallery :slotted(*) {
        flex-basis: 86%;
    }
}
</style>
