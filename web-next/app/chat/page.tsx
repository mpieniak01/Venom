import { CockpitWrapper } from "@/components/cockpit/cockpit-wrapper";

export default function ChatPage() {
  // Conversation controls render immediately; telemetry loads independently in
  // its existing client subscriptions instead of blocking the route response.
  return <CockpitWrapper variant="reference" />;
}
