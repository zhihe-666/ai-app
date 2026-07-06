import { Modal, Result, Tag } from 'antd'
import { RocketOutlined } from '@ant-design/icons'

interface ComingSoonProps {
  featureName: string
  expectedDate: string
  description: string
}

export function showComingSoon(props: ComingSoonProps) {
  Modal.info({
    title: null,
    icon: null,
    width: 420,
    content: (
      <Result
        icon={<RocketOutlined style={{ color: '#6366f1' }} />}
        title={`${props.featureName} · 即将上线`}
        subTitle={props.description}
        extra={<Tag color="blue">预计 {props.expectedDate} 可用</Tag>}
      />
    ),
    okText: '知道了',
  })
}

export default showComingSoon