<template>
  <div class="legal-page">
    <LandingNav />
    <main class="legal-main">
      <div class="legal-container">
        <header class="legal-header">
          <span class="legal-badge">Legal</span>
          <h1 class="legal-title">Terms of Service</h1>
          <p class="legal-updated">Last updated: March 18, 2026</p>
        </header>

        <div class="legal-body">
          <section class="legal-section">
            <h2>1. Acceptance of Terms</h2>
            <p>
              By accessing or using Pythinker ("the Service"), you agree to be bound by these Terms of Service ("Terms"). If you do not agree to these Terms, you may not access or use the Service.
            </p>
            <p>
              These Terms constitute a legally binding agreement between you and Pythinker ("we," "our," or "us"). We reserve the right to modify these Terms at any time. Your continued use of the Service after changes constitutes acceptance of the updated Terms.
            </p>
          </section>

          <section class="legal-section">
            <h2>2. Description of Service</h2>
            <p>
              Pythinker is an open-source, self-hosted AI agent platform that executes tasks using browser automation, terminal commands, file operations, and web research within isolated Docker sandbox environments. The Service includes:
            </p>
            <ul>
              <li>AI-powered agent sessions with tool execution capabilities</li>
              <li>Isolated sandbox environments for secure task execution</li>
              <li>Browser automation via Chrome DevTools Protocol</li>
              <li>File management and code generation tools</li>
              <li>Research and web search capabilities</li>
              <li>Real-time streaming of agent activity and results</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>3. Account Registration</h2>
            <p>
              To use certain features of the Service, you may need to create an account. You agree to:
            </p>
            <ul>
              <li>Provide accurate and complete registration information</li>
              <li>Maintain the security of your account credentials</li>
              <li>Promptly update your account information if it changes</li>
              <li>Accept responsibility for all activities that occur under your account</li>
              <li>Notify us immediately of any unauthorized use of your account</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>4. Acceptable Use</h2>
            <p>You agree to use the Service only for lawful purposes. You shall not:</p>
            <ul>
              <li>Use the Service to violate any applicable law, regulation, or third-party rights</li>
              <li>Attempt to gain unauthorized access to systems, networks, or data outside your sandbox environment</li>
              <li>Use the Service to distribute malware, viruses, or other harmful code</li>
              <li>Conduct denial-of-service attacks or deliberately overload the Service infrastructure</li>
              <li>Use agent tools to scrape, crawl, or harvest data from websites in violation of their terms of service</li>
              <li>Generate, store, or distribute content that is illegal, harmful, threatening, abusive, or otherwise objectionable</li>
              <li>Attempt to bypass sandbox isolation, resource limits, or security controls</li>
              <li>Reverse-engineer, decompile, or disassemble the Service except as permitted by applicable law</li>
              <li>Use the Service to conduct unauthorized penetration testing or security scanning of third-party systems</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>5. Sandbox Environments</h2>
            <p>
              Agent tasks execute within isolated Docker containers ("sandboxes"). You acknowledge and agree that:
            </p>
            <ul>
              <li>Sandboxes are ephemeral and may be terminated at any time</li>
              <li>Data within sandboxes is not guaranteed to persist beyond the session lifecycle</li>
              <li>Resource usage (CPU, memory, network) is subject to configured limits</li>
              <li>Network access from sandboxes may be restricted based on deployment configuration</li>
              <li>You are responsible for saving any important outputs before a session ends</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>6. Intellectual Property</h2>

            <h3>6.1 Your Content</h3>
            <p>
              You retain all rights to the content you create, upload, or generate through the Service, including code, documents, and research outputs. By using the Service, you grant us a limited license to process your content solely to provide and improve the Service.
            </p>

            <h3>6.2 Open-Source License</h3>
            <p>
              Pythinker is open-source software. The source code is available under its respective license on GitHub. These Terms govern your use of the hosted Service and do not restrict your rights under the open-source license.
            </p>

            <h3>6.3 AI-Generated Content</h3>
            <p>
              Content generated by AI agents through the Service is provided as-is. You are responsible for reviewing, validating, and taking ownership of any AI-generated code, text, or artifacts before using them in production or sharing them with others.
            </p>
          </section>

          <section class="legal-section">
            <h2>7. Third-Party Services</h2>
            <p>
              The Service integrates with third-party APIs and services, including but not limited to:
            </p>
            <ul>
              <li><strong>LLM Providers:</strong> AI model APIs for response generation (e.g., OpenAI-compatible endpoints)</li>
              <li><strong>Search Providers:</strong> Web search APIs for research capabilities</li>
              <li><strong>Embedding Services:</strong> Vector embedding APIs for memory and retrieval</li>
              <li><strong>Authentication Providers:</strong> Third-party login services (e.g., GitHub, Google)</li>
            </ul>
            <p>
              Your use of these third-party services is subject to their respective terms of service and privacy policies. We are not responsible for the availability, accuracy, or practices of third-party services.
            </p>
          </section>

          <section class="legal-section">
            <h2>8. Self-Hosted Deployments</h2>
            <p>
              If you deploy Pythinker on your own infrastructure:
            </p>
            <ul>
              <li>You are responsible for the security, maintenance, and compliance of your deployment</li>
              <li>You must configure API keys and credentials securely</li>
              <li>You are responsible for keeping the software up to date</li>
              <li>We are not liable for issues arising from misconfigured self-hosted deployments</li>
              <li>You may modify the software subject to the open-source license terms</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>9. Disclaimer of Warranties</h2>
            <p>
              THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND, WHETHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.
            </p>
            <p>
              We do not warrant that:
            </p>
            <ul>
              <li>The Service will be uninterrupted, timely, secure, or error-free</li>
              <li>AI-generated outputs will be accurate, complete, or suitable for your purposes</li>
              <li>The results obtained from the Service will meet your requirements</li>
              <li>Any defects in the Service will be corrected</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>10. Limitation of Liability</h2>
            <p>
              TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL PYTHINKER, ITS DEVELOPERS, CONTRIBUTORS, OR AFFILIATES BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING BUT NOT LIMITED TO LOSS OF PROFITS, DATA, USE, GOODWILL, OR OTHER INTANGIBLE LOSSES, RESULTING FROM:
            </p>
            <ul>
              <li>Your use of or inability to use the Service</li>
              <li>Any unauthorized access to or alteration of your data</li>
              <li>Actions taken by AI agents on your behalf</li>
              <li>Any third-party conduct or content on or through the Service</li>
              <li>Any content obtained from the Service</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>11. Indemnification</h2>
            <p>
              You agree to indemnify, defend, and hold harmless Pythinker and its developers, contributors, and affiliates from and against any claims, damages, obligations, losses, liabilities, costs, or expenses arising from:
            </p>
            <ul>
              <li>Your use of the Service</li>
              <li>Your violation of these Terms</li>
              <li>Your violation of any third-party rights</li>
              <li>Content you create, upload, or generate through the Service</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>12. Termination</h2>
            <p>
              We reserve the right to suspend or terminate your access to the Service at any time, with or without cause, with or without notice. Upon termination:
            </p>
            <ul>
              <li>Your right to use the Service will immediately cease</li>
              <li>Active sandbox environments will be terminated</li>
              <li>You may request an export of your data before termination takes effect</li>
              <li>Provisions that by their nature should survive termination shall survive</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>13. Governing Law</h2>
            <p>
              These Terms shall be governed by and construed in accordance with the laws of the jurisdiction in which the Service operator resides, without regard to its conflict of law provisions. Any legal action or proceeding arising under these Terms shall be brought exclusively in the courts of that jurisdiction.
            </p>
          </section>

          <section class="legal-section">
            <h2>14. Severability</h2>
            <p>
              If any provision of these Terms is held to be invalid or unenforceable, the remaining provisions shall continue in full force and effect. The invalid or unenforceable provision shall be modified to the minimum extent necessary to make it valid and enforceable.
            </p>
          </section>

          <section class="legal-section">
            <h2>15. Contact</h2>
            <p>
              If you have questions about these Terms of Service, please contact us at:
            </p>
            <div class="legal-contact">
              <p><strong>Pythinker</strong></p>
              <p>Email: <a href="mailto:legal@pythinker.com" class="legal-link">legal@pythinker.com</a></p>
              <p>GitHub: <a href="https://github.com/mohamed-elkholy95/Pythinker" target="_blank" rel="noopener noreferrer" class="legal-link">github.com/mohamed-elkholy95/Pythinker</a></p>
            </div>
          </section>
        </div>
      </div>
    </main>
    <LandingFooter />
  </div>
</template>

<script setup lang="ts">
import LandingNav from '../components/landing/LandingNav.vue'
import LandingFooter from '../components/landing/LandingFooter.vue'
</script>

<style scoped>
.legal-page {
  min-height: 100vh;
  background: var(--background-main);
  color: var(--text-primary);
  font-family: var(--font-sans);
}

.legal-main {
  padding-top: 100px;
  padding-bottom: 80px;
}

.legal-container {
  max-width: 760px;
  margin: 0 auto;
  padding: 0 24px;
}

.legal-header {
  margin-bottom: 48px;
  padding-bottom: 32px;
  border-bottom: 1px solid var(--border-light);
}

.legal-badge {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-tertiary);
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.05));
  padding: 4px 12px;
  border-radius: var(--radius-full);
  margin-bottom: 16px;
}

.legal-title {
  font-family: var(--font-display);
  font-size: 42px;
  font-weight: 400;
  line-height: 1.15;
  letter-spacing: -0.02em;
  margin: 0 0 12px;
  color: var(--text-primary);
}

.legal-updated {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

.legal-body {
  font-size: 15px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.legal-section {
  margin-bottom: 36px;
}

.legal-section h2 {
  font-family: var(--font-sans);
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 14px;
  letter-spacing: -0.01em;
}

.legal-section h3 {
  font-family: var(--font-sans);
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 20px 0 10px;
}

.legal-section p {
  margin: 0 0 12px;
}

.legal-section ul {
  margin: 0 0 12px;
  padding-left: 24px;
}

.legal-section li {
  margin-bottom: 8px;
}

.legal-section li strong {
  color: var(--text-primary);
}

.legal-link {
  color: var(--text-primary);
  text-decoration: underline;
  text-underline-offset: 2px;
  transition: opacity 0.2s;
}

.legal-link:hover {
  opacity: 0.7;
}

.legal-contact {
  background: var(--background-secondary);
  border-radius: var(--radius-lg);
  padding: 20px 24px;
  margin-top: 12px;
}

.legal-contact p {
  margin: 0 0 4px;
  font-size: 14px;
}

.legal-contact p:last-child {
  margin-bottom: 0;
}

@media (max-width: 768px) {
  .legal-main {
    padding-top: 80px;
    padding-bottom: 48px;
  }

  .legal-title {
    font-size: 32px;
  }

  .legal-container {
    padding: 0 16px;
  }
}
</style>
