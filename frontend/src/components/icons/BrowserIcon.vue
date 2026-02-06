<template>
    <svg :width="size" :height="size" viewBox="0 0 19 18" fill="none" xmlns="http://www.w3.org/2000/svg"
        :style="{ minWidth: `${size}px`, minHeight: `${size}px` }">
        <g :filter="`url(#${filterId})`">
            <rect x="1.5" y="1.5" width="15" height="15" rx="7.5" :fill="`url(#${gradientId})`"></rect>
        </g>
        <rect x="1.92857" y="1.92857" width="14.1429" height="14.1429" rx="7.07143" stroke="#B9B9B7"
            stroke-width="0.857143"></rect>
        <path
            d="M7.52172 7.76297C7.56208 7.65057 7.65057 7.56208 7.76297 7.52172L11.2014 6.28681C11.5197 6.17249 11.8274 6.48026 11.7131 6.79854L10.4776 10.2365C10.4373 10.3488 10.3488 10.4373 10.2365 10.4776L6.79854 11.7131C6.48026 11.8274 6.17249 11.5197 6.28681 11.2014L7.52172 7.76297Z"
            stroke="#535350" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"></path>
        <defs>
            <filter :id="filterId" x="1" y="1" width="16" height="16" filterUnits="userSpaceOnUse"
                color-interpolation-filters="sRGB">
                <feFlood flood-opacity="0" result="BackgroundImageFix"></feFlood>
                <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape"></feBlend>
                <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0"
                    result="hardAlpha"></feColorMatrix>
                <feOffset dx="1" dy="1"></feOffset>
                <feGaussianBlur stdDeviation="0.25"></feGaussianBlur>
                <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1"></feComposite>
                <feColorMatrix type="matrix" values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.6 0"></feColorMatrix>
                <feBlend mode="normal" in2="shape" :result="`effect1_${uid}`"></feBlend>
                <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0"
                    result="hardAlpha"></feColorMatrix>
                <feOffset dx="-1" dy="-1"></feOffset>
                <feGaussianBlur stdDeviation="0.25"></feGaussianBlur>
                <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1"></feComposite>
                <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.08 0"></feColorMatrix>
                <feBlend mode="normal" :in2="`effect1_${uid}`" :result="`effect2_${uid}`">
                </feBlend>
            </filter>
            <linearGradient :id="gradientId" x1="9" y1="1.5" x2="9" y2="16.5"
                gradientUnits="userSpaceOnUse">
                <stop stop-color="white" stop-opacity="0"></stop>
                <stop offset="1" stop-opacity="0.16"></stop>
            </linearGradient>
        </defs>
    </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue';

defineProps({
    size: {
        type: Number,
        default: 21
    }
});

// Generate unique IDs for this instance to avoid SVG filter/gradient conflicts
const uid = Math.random().toString(36).substring(2, 9);
const filterId = computed(() => `browser_filter_${uid}`);
const gradientId = computed(() => `browser_gradient_${uid}`);
</script>