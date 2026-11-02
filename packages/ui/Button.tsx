import * as React from "react";

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
};

// Single shared Button. App-specific buttons are composed here, never forked.
export function Button({ variant = "primary", ...rest }: Props) {
  return <button data-variant={variant} {...rest} />;
}
