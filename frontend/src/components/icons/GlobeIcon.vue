<template>
    <svg :width="size" :height="size" viewBox="0 0 19 18" fill="none" xmlns="http://www.w3.org/2000/svg"
        :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
        <g filter="url(#filter0_ii_globe)">
            <rect x="1.5" y="1.5" width="15" height="15" rx="7.5" fill="url(#paint0_linear_globe)"></rect>
        </g>
        <rect class="icon-border" x="1.92857" y="1.92857" width="14.1429" height="14.1429" rx="7.07143"
            stroke-width="0.857143"></rect>
        <!-- Globe icon - circle with latitude/longitude lines -->
        <circle class="icon-detail" cx="9" cy="9" r="4" stroke-width="1.1" fill="none"></circle>
        <ellipse class="icon-detail" cx="9" cy="9" rx="2" ry="4" stroke-width="1.1" fill="none"></ellipse>
        <line class="icon-detail" x1="5" y1="9" x2="13" y2="9" stroke-width="1.1"></line>
        <defs>
            <filter id="filter0_ii_globe" x="1" y="1" width="16" height="16" filterUnits="userSpaceOnUse"
                color-interpolation-filters="sRGB">
                <feFlood flood-opacity="0" result="BackgroundImageFix"></feFlood>
                <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape"></feBlend>
                <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0"
                    result="hardAlpha"></feColorMatrix>
                <feOffset dx="1" dy="1"></feOffset>
                <feGaussianBlur stdDeviation="0.25"></feGaussianBlur>
                <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1"></feComposite>
                <feColorMatrix type="matrix" values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.6 0"></feColorMatrix>
                <feBlend mode="normal" in2="shape" result="effect1_innerShadow_globe"></feBlend>
                <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0"
                    result="hardAlpha"></feColorMatrix>
                <feOffset dx="-1" dy="-1"></feOffset>
                <feGaussianBlur stdDeviation="0.25"></feGaussianBlur>
                <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1"></feComposite>
                <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.08 0"></feColorMatrix>
                <feBlend mode="normal" in2="effect1_innerShadow_globe" result="effect2_innerShadow_globe">
                </feBlend>
            </filter>
            <linearGradient id="paint0_linear_globe" x1="9" y1="1.5" x2="9" y2="16.5"
                gradientUnits="userSpaceOnUse">
                <stop stop-color="white" stop-opacity="0"></stop>
                <stop offset="1" stop-opacity="0.16"></stop>
            </linearGradient>
        </defs>
    </svg>
</template>

<script setup lang="ts">
defineProps({
    size: {
        type: Number,
        default: 21
    }
});
</script>

<style scoped>
.icon-border {
    stroke: var(--border-main, #B9B9B7);
}
.icon-detail {
    stroke: var(--icon-secondary, #535350);
}
</style>
