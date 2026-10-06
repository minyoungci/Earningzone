import { motion } from 'framer-motion'
import { EASE_OUT } from '../../lib/motion'

export default function GlassCard({ children, className = '', delay = 0, hover = false, ...rest }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay, ease: EASE_OUT }}
      className={`glass p-5 ${hover ? 'glass-hover cursor-pointer' : ''} ${className}`}
      {...rest}
    >
      {children}
    </motion.div>
  )
}
