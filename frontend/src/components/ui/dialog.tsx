import * as React from "react";

export const Dialog = ({ open, onOpenChange, children }: { open: boolean; onOpenChange: (open: boolean) => void; children: React.ReactNode }) => (
  open ? <div className="dialog-backdrop">{children}</div> : null
);

export const DialogContent = ({ children }: { children: React.ReactNode }) => (
  <div className="dialog-content">{children}</div>
);

export const DialogHeader = ({ children }: { children: React.ReactNode }) => (
  <div className="dialog-header">{children}</div>
);

export const DialogTitle = ({ children }: { children: React.ReactNode }) => (
  <h2 className="dialog-title">{children}</h2>
);

export const DialogDescription = ({ children }: { children: React.ReactNode }) => (
  <p className="dialog-description">{children}</p>
);

export const DialogFooter = ({ children }: { children: React.ReactNode }) => (
  <div className="dialog-footer">{children}</div>
);

export const DialogTrigger = ({ children }: { children: React.ReactNode }) => (
  <button className="dialog-trigger">{children}</button>
);
