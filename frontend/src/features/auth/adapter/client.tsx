import type { ReactNode } from "react";
import type { AuthClientModule, ConsentIdentity } from "../auth-adapter";

/**
 * Client-side surface for the no-provider configuration.
 *
 * Every slot answers harmlessly rather than being absent, so the platform's call
 * sites never branch on whether an adapter is installed. The provider renders its
 * children untouched and the top bar renders nothing, which is what makes the
 * single-tenant UI simply lack a sign-in affordance rather than break without one.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function AuthTopBar() {
  return null;
}

/**
 * The four routes below are unreachable in single-tenant mode: nothing redirects to
 * `/sign-in`, the root route never points at `/select-org`, and the backend
 * auto-approves MCP consent without sending a browser to `/mcp-consent`. They still
 * exist as routes, so each says why rather than rendering blank.
 */
function NotConfigured({ what }: { what: string }) {
  return (
    <div className="max-w-md text-sm text-muted-foreground">
      <p className="mb-2 font-medium text-foreground">No auth adapter configured</p>
      <p>
        {what} needs an authentication provider. This deployment runs single-tenant: every request
        is the local user in the local group. See <code>src/features/auth/adapter/README.md</code>.
      </p>
    </div>
  );
}

export function SignInView() {
  return <NotConfigured what="Signing in" />;
}

export function SignUpView() {
  return <NotConfigured what="Signing up" />;
}

/**
 * The props are accepted and ignored. Declaring them matters: a component taking
 * no props is assignable to `ComponentType<P>`, so the conformance assertion below
 * would accept a zero-prop version while every call site failed to type-check.
 */
export function GroupPickerView(_props: { hrefForGroup: (slug: string) => string }) {
  return <NotConfigured what="Choosing a group" />;
}

export function ConsentGate(_props: {
  requestId: string;
  children: (identity: ConsentIdentity) => ReactNode;
}) {
  return <NotConfigured what="Authorizing MCP access" />;
}

const _conforms: AuthClientModule = {
  AuthProvider,
  AuthTopBar,
  SignInView,
  SignUpView,
  GroupPickerView,
  ConsentGate,
};
void _conforms;
