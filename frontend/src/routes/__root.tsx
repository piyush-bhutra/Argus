import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";

const primaryBtn =
  "rounded-paper bg-ink-strong px-5 pt-2 pb-1.5 font-marker text-[27px] leading-none text-paper shadow-button hover:bg-[#1f1e1c]";
const secondaryBtn =
  "rounded-paper border-[1.5px] border-ink-strong px-5 pt-2 pb-1.5 font-marker text-[27px] leading-none text-ink-strong hover:bg-chip-bg";

function NotFoundComponent() {
  return (
    <div className="paper-ruled flex min-h-screen items-center justify-center px-4">
      <div className="max-w-md text-center">
        <h1 className="font-marker text-hero text-ink-strong">404</h1>
        <h2 className="mt-4 text-h2 text-ink">Page not found</h2>
        <p className="mt-2 text-ink-soft">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link to="/" className={primaryBtn}>
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="paper-ruled flex min-h-screen items-center justify-center px-4">
      <div className="max-w-md text-center">
        <h1 className="text-h2 text-ink">This page didn't load</h1>
        <p className="mt-2 text-ink-soft">
          Something went wrong on our end. You can try refreshing or head back home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className={primaryBtn}
          >
            Try again
          </button>
          <a href="/" className={secondaryBtn}>
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Argus" },
      {
        name: "description",
        content:
          "Adversarial debate dashboard for claim verification: transcript, attack graph, calibrated verdict.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      {
        rel: "stylesheet",
        href: appCss,
      },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Just+Another+Hand&family=Architects+Daughter&family=IBM+Plex+Mono:wght@400;500;600&display=swap",
      },
      { rel: "icon", href: "/favicon.svg", type: "image/svg+xml" },
    ],
  }),

  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      {/* Required: nested routes render here. Removing <Outlet /> breaks all child routes. */}
      <Outlet />
    </QueryClientProvider>
  );
}
