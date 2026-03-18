<template>
  <div class="legal-page">
    <LandingNav />
    <main class="legal-main">
      <div class="legal-container">
        <header class="legal-header">
          <span class="legal-badge">Legal</span>
          <h1 class="legal-title">Privacy Policy</h1>
          <p class="legal-updated">Last updated: March 18, 2026</p>
        </header>

        <div class="legal-body">
          <section class="legal-section">
            <h2>1. Introduction</h2>
            <p>
              Pythinker ("we," "our," or "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our self-hosted AI agent platform and related services (collectively, the "Service").
            </p>
            <p>
              By accessing or using the Service, you agree to this Privacy Policy. If you do not agree with the terms of this Privacy Policy, please do not access the Service.
            </p>
          </section>

          <section class="legal-section">
            <h2>2. Information We Collect</h2>

            <h3>2.1 Information You Provide</h3>
            <ul>
              <li><strong>Account Information:</strong> When you create an account, we collect your name, email address, and authentication credentials.</li>
              <li><strong>Chat and Session Data:</strong> Messages, prompts, and instructions you submit through the Service, as well as agent-generated responses and tool outputs.</li>
              <li><strong>Files and Documents:</strong> Any files you upload or create within sandbox environments during your sessions.</li>
              <li><strong>Preferences:</strong> Settings and configurations you customize within the Service.</li>
            </ul>

            <h3>2.2 Information Collected Automatically</h3>
            <ul>
              <li><strong>Usage Data:</strong> We collect information about how you interact with the Service, including session duration, features used, and tool invocations.</li>
              <li><strong>Device Information:</strong> Browser type, operating system, screen resolution, and device identifiers.</li>
              <li><strong>Log Data:</strong> Server logs that may include your IP address, access times, and pages viewed.</li>
            </ul>

            <h3>2.3 Information from Third-Party Services</h3>
            <p>
              If you authenticate via third-party providers (e.g., GitHub, Google), we receive basic profile information as authorized by you during the authentication flow.
            </p>
          </section>

          <section class="legal-section">
            <h2>3. How We Use Your Information</h2>
            <p>We use the collected information for the following purposes:</p>
            <ul>
              <li>To provide, operate, and maintain the Service</li>
              <li>To process and execute your AI agent tasks within isolated sandbox environments</li>
              <li>To improve and personalize your experience, including memory-based context recall</li>
              <li>To communicate with you about updates, security alerts, and support</li>
              <li>To monitor and analyze usage patterns for performance optimization</li>
              <li>To detect, prevent, and address technical issues and security threats</li>
              <li>To comply with legal obligations</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>4. Data Isolation and Sandbox Security</h2>
            <p>
              All agent tasks execute within isolated Docker sandbox environments. Each session operates in its own container with restricted network access and resource limits. Sandbox environments are ephemeral — they are destroyed after your session ends, and no persistent data remains on the execution infrastructure unless explicitly saved.
            </p>
            <p>
              Browser interactions within sandboxes use Chrome DevTools Protocol (CDP) for screencast streaming. Browser data, cookies, and local storage within sandboxes are not persisted beyond the session lifecycle.
            </p>
          </section>

          <section class="legal-section">
            <h2>5. Data Storage and Retention</h2>
            <ul>
              <li><strong>Session Data:</strong> Chat history and session events are stored in MongoDB and retained for as long as your account is active or as needed to provide the Service.</li>
              <li><strong>Memory Data:</strong> User knowledge and preferences stored in Qdrant (vector database) are retained until you request deletion.</li>
              <li><strong>Sandbox Artifacts:</strong> Files generated during sessions are stored temporarily and removed when the sandbox is destroyed.</li>
              <li><strong>Logs:</strong> Server and application logs are retained for up to 90 days for debugging and security purposes.</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>6. Data Sharing and Disclosure</h2>
            <p>We do not sell your personal information. We may share your information in the following circumstances:</p>
            <ul>
              <li><strong>LLM Providers:</strong> Prompts and context are sent to configured AI model providers (e.g., OpenAI-compatible APIs) for response generation. These providers process data according to their own privacy policies.</li>
              <li><strong>Search Providers:</strong> When using research features, queries are sent to configured search APIs (e.g., Serper, Tavily, Brave).</li>
              <li><strong>Legal Compliance:</strong> When required by law, regulation, or legal process.</li>
              <li><strong>Protection:</strong> To protect the rights, property, or safety of Pythinker, our users, or the public.</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>7. Self-Hosted Deployments</h2>
            <p>
              Pythinker is designed as a self-hosted platform. When you deploy Pythinker on your own infrastructure, you maintain full control over your data. In self-hosted deployments:
            </p>
            <ul>
              <li>All data remains on your infrastructure</li>
              <li>You are responsible for data security and compliance</li>
              <li>External API calls (LLM, search, embeddings) are made directly from your infrastructure to the configured providers</li>
              <li>No data is sent to Pythinker's servers</li>
            </ul>
          </section>

          <section class="legal-section">
            <h2>8. Your Rights and Choices</h2>
            <p>Depending on your jurisdiction, you may have the following rights:</p>
            <ul>
              <li><strong>Access:</strong> Request a copy of the personal data we hold about you</li>
              <li><strong>Correction:</strong> Request correction of inaccurate personal data</li>
              <li><strong>Deletion:</strong> Request deletion of your personal data and account</li>
              <li><strong>Export:</strong> Request a portable copy of your data</li>
              <li><strong>Objection:</strong> Object to processing of your personal data</li>
              <li><strong>Restriction:</strong> Request restriction of processing your personal data</li>
            </ul>
            <p>
              To exercise any of these rights, please contact us at <a href="mailto:privacy@pythinker.com" class="legal-link">privacy@pythinker.com</a>.
            </p>
          </section>

          <section class="legal-section">
            <h2>9. Security</h2>
            <p>
              We implement industry-standard security measures to protect your data, including:
            </p>
            <ul>
              <li>OWASP-compliant security headers on all HTTP responses</li>
              <li>JWT-based authentication with secret validation at startup</li>
              <li>Sandboxed execution environments with resource isolation</li>
              <li>Non-root container execution</li>
              <li>Encrypted data transmission (TLS/HTTPS)</li>
            </ul>
            <p>
              While we strive to protect your information, no method of electronic storage or transmission is 100% secure. We cannot guarantee absolute security.
            </p>
          </section>

          <section class="legal-section">
            <h2>10. Cookies and Tracking</h2>
            <p>
              We use minimal cookies and local storage for essential functionality:
            </p>
            <ul>
              <li><strong>Authentication tokens:</strong> To maintain your login session</li>
              <li><strong>Theme preference:</strong> To remember your light/dark mode choice</li>
              <li><strong>Session state:</strong> To preserve your workspace across page refreshes</li>
            </ul>
            <p>We do not use third-party advertising or analytics tracking cookies.</p>
          </section>

          <section class="legal-section">
            <h2>11. Children's Privacy</h2>
            <p>
              The Service is not intended for use by individuals under the age of 16. We do not knowingly collect personal information from children. If we become aware that we have collected personal information from a child under 16, we will take steps to delete that information promptly.
            </p>
          </section>

          <section class="legal-section">
            <h2>12. Changes to This Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page and updating the "Last updated" date. You are advised to review this Privacy Policy periodically.
            </p>
          </section>

          <section class="legal-section">
            <h2>13. Contact Us</h2>
            <p>
              If you have questions or concerns about this Privacy Policy, please contact us at:
            </p>
            <div class="legal-contact">
              <p><strong>Pythinker</strong></p>
              <p>Email: <a href="mailto:privacy@pythinker.com" class="legal-link">privacy@pythinker.com</a></p>
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
