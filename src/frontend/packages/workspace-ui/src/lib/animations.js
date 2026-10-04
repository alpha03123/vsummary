/**
 * Framer Motion Variants Collection
 * Physics-based animations tailored for a "soft bouncy" iOS-like feel.
 */

// Soft spring configuration for layout and enter transitions
export const springTransition = {
  type: "spring",
  stiffness: 400,
  damping: 28,
  mass: 1,
};

// Even softer, bouncy spring for interactive elements (hover, tap)
// Adjusted for a cleaner, tighter iOS feel instead of overly rubbery
export const bouncySpring = {
  type: "spring",
  stiffness: 350,
  damping: 25, // Increased damping = less rubber-banding, stops cleaner
  mass: 0.8,
};

export const staggerContainer = {
  initial: {},
  animate: {
    transition: {
      staggerChildren: 0.05,
      delayChildren: 0.05,
    },
  },
  exit: {
    transition: {
      staggerChildren: 0.03,
      staggerDirection: -1,
    },
  },
};

export const fadeUpVariant = {
  initial: {
    opacity: 0,
    y: 20,
    scale: 0.98,
  },
  animate: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: springTransition,
  },
  exit: {
    opacity: 0,
    y: -10,
    scale: 0.98,
    transition: { duration: 0.2 },
  },
  hover: {
    scale: 1.015,
    y: -2,
    transition: bouncySpring,
  },
  tap: {
    scale: 0.97,
    transition: bouncySpring,
  },
};

// Just pure hover scale effects for simpler cards
export const cardPopVariant = {
  hover: {
    scale: 1.01,
    transition: bouncySpring,
  },
  tap: {
    scale: 0.98,
    transition: bouncySpring,
  },
};

export const popScaleVariant = {
  initial: { opacity: 0, scale: 0.9 },
  animate: {
    opacity: 1,
    scale: 1,
    transition: springTransition
  },
  exit: { opacity: 0, scale: 0.9, transition: { duration: 0.15 } }
};

export const blurVariant = {
  initial: { opacity: 0, filter: "blur(8px)" },
  animate: {
    opacity: 1,
    filter: "blur(0px)",
    transition: { duration: 0.25, ease: "easeInOut" }
  },
  exit: {
    opacity: 0,
    filter: "blur(4px)",
    transition: { duration: 0.15, ease: "easeIn" }
  },
  hover: {
    scale: 1.015,
    filter: "blur(0px)",
    transition: bouncySpring,
  },
  tap: {
    scale: 0.98,
    transition: bouncySpring,
  }
};
